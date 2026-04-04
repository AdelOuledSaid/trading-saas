import stripe
from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_required, current_user

import config
from app.extensions import db
from app.models import User
from app.services.telegram_service import send_telegram_message
from app.services.stripe_service import (
    normalize_plan,
    get_price_id_for_plan,
    sync_user_premium_status,
    has_active_stripe_subscription,
    get_subscription_status,
)

billing_bp = Blueprint("billing", __name__)
stripe.api_key = config.STRIPE_SECRET_KEY


@billing_bp.route("/pricing")
def pricing():
    if current_user.is_authenticated:
        sync_user_premium_status(current_user)

    return render_template(
        "pricing.html",
        stripe_publishable_key=config.STRIPE_PUBLISHABLE_KEY,
        user_plan=current_user.plan if current_user.is_authenticated else "free"
    )


@billing_bp.route("/create-checkout-session", methods=["POST"])
@login_required
def create_checkout_session():
    selected_plan = normalize_plan(request.form.get("plan"))
    price_id = get_price_id_for_plan(selected_plan)

    if selected_plan == "free" or not price_id:
        flash("Plan invalide.")
        return redirect(url_for("billing.pricing"))

    if has_active_stripe_subscription(current_user):
        flash("Un abonnement actif existe déjà sur votre compte.")
        return redirect(url_for("billing.pricing"))

    if not config.STRIPE_SECRET_KEY:
        flash("Stripe n'est pas configuré correctement.")
        return redirect(url_for("billing.pricing"))

    try:
        if not current_user.stripe_customer_id:
            customer = stripe.Customer.create(email=current_user.email)
            current_user.stripe_customer_id = customer["id"]
            db.session.commit()
            current_app.logger.info("Nouveau client Stripe créé : %s", current_user.stripe_customer_id)

        session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            customer=current_user.stripe_customer_id,
            client_reference_id=str(current_user.id),
            metadata={
                "user_id": str(current_user.id),
                "user_email": current_user.email,
                "plan": selected_plan,
            },
            success_url=f"{config.DOMAIN}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{config.DOMAIN}/cancel",
        )

        return redirect(session.url, code=303)

    except Exception as e:
        current_app.logger.error("Erreur Stripe create_checkout_session: %s", repr(e))
        flash("Impossible de créer la session de paiement.")
        return redirect(url_for("billing.pricing"))


@billing_bp.route("/create-customer-portal-session", methods=["POST"])
@login_required
def create_customer_portal_session():
    if not current_user.stripe_customer_id:
        flash("Aucun client Stripe lié à ce compte.")
        return redirect(url_for("billing.pricing"))

    if not config.STRIPE_SECRET_KEY:
        flash("Stripe n'est pas configuré correctement.")
        return redirect(url_for("billing.pricing"))

    try:
        session = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url=f"{config.DOMAIN}/pricing"
        )
        return redirect(session.url, code=303)

    except Exception as e:
        current_app.logger.error("Erreur Stripe customer portal: %s", repr(e))
        flash("Impossible d'ouvrir le portail client.")
        return redirect(url_for("billing.pricing"))


@billing_bp.route("/success")
@login_required
def success():
    session_id = request.args.get("session_id")
    session_data = None
    vip_link = None

    if session_id and config.STRIPE_SECRET_KEY:
        try:
            session_data = stripe.checkout.Session.retrieve(session_id)

            customer_id = session_data.get("customer")
            subscription_id = session_data.get("subscription")
            metadata = session_data.get("metadata", {})
            selected_plan = normalize_plan(metadata.get("plan"))

            if customer_id and not current_user.stripe_customer_id:
                current_user.stripe_customer_id = customer_id

            if subscription_id and not current_user.stripe_subscription_id:
                current_user.stripe_subscription_id = subscription_id

            status = get_subscription_status(subscription_id) if subscription_id else None
            current_user.is_premium = status in ["trialing", "active", "past_due"]

            if current_user.is_premium and selected_plan != "free":
                current_user.plan = selected_plan

            db.session.commit()

        except Exception as e:
            current_app.logger.error("Erreur récupération session Stripe: %s", repr(e))

    if (current_user.plan or "").lower() == "vip" and config.TELEGRAM_VIP_INVITE_LINK:
        vip_link = config.TELEGRAM_VIP_INVITE_LINK

    return render_template("success.html", session_data=session_data, vip_link=vip_link)


@billing_bp.route("/cancel")
@login_required
def cancel():
    return render_template("cancel.html")


@billing_bp.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    if not config.STRIPE_WEBHOOK_SECRET:
        current_app.logger.error("Webhook secret Stripe manquant")
        return "", 500

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=config.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        current_app.logger.error("Payload Stripe invalide")
        return "", 400
    except stripe.error.SignatureVerificationError:
        current_app.logger.error("Signature Stripe invalide")
        return "", 400

    event_type = event["type"]
    data_object = event["data"]["object"]
    current_app.logger.info("Stripe event reçu: %s", event_type)

    try:
        if event_type == "checkout.session.completed":
            metadata = data_object.get("metadata", {})
            user_id = metadata.get("user_id") or data_object.get("client_reference_id")
            customer_id = data_object.get("customer")
            subscription_id = data_object.get("subscription")
            selected_plan = normalize_plan(metadata.get("plan"))

            customer_email = data_object.get("customer_email")
            if not customer_email:
                customer_details = data_object.get("customer_details", {})
                customer_email = customer_details.get("email")

            user = None
            if user_id:
                try:
                    user = db.session.get(User, int(user_id))
                except Exception as e:
                    current_app.logger.error("Erreur conversion user_id Stripe: %s", repr(e))

            if not user and customer_email:
                user = User.query.filter_by(email=customer_email.strip().lower()).first()

            if user:
                user.stripe_customer_id = customer_id
                user.stripe_subscription_id = subscription_id
                user.plan = selected_plan if selected_plan != "free" else "basic"
                user.is_premium = True
                db.session.commit()

                send_telegram_message(
                    f"""
✅ <b>CHECKOUT STRIPE TERMINÉ</b>

👤 <b>Utilisateur :</b> {user.email}
🧾 <b>Subscription :</b> {subscription_id}
💎 <b>Plan :</b> {user.plan.upper()}
💳 <b>Statut :</b> Premium activé
""".strip()
                )

                if user.plan == "vip":
                    send_telegram_message(
                        f"""
👑 <b>NOUVEAU CLIENT VIP</b>

👤 <b>Utilisateur :</b> {user.email}
🧾 <b>Subscription :</b> {subscription_id}
🔗 <b>Action :</b> envoyer / vérifier l'accès Telegram VIP
""".strip()
                    )

        elif event_type == "customer.subscription.updated":
            customer_id = data_object.get("customer")
            subscription_id = data_object.get("id")
            status = data_object.get("status")

            user = None
            if subscription_id:
                user = User.query.filter_by(stripe_subscription_id=subscription_id).first()
            if not user and customer_id:
                user = User.query.filter_by(stripe_customer_id=customer_id).first()

            if user:
                user.stripe_customer_id = customer_id
                user.stripe_subscription_id = subscription_id
                user.is_premium = status in ["trialing", "active", "past_due"]

                if user.is_premium and user.plan == "free":
                    user.plan = "basic"

                db.session.commit()

        elif event_type == "customer.subscription.deleted":
            customer_id = data_object.get("customer")
            subscription_id = data_object.get("id")

            user = None
            if subscription_id:
                user = User.query.filter_by(stripe_subscription_id=subscription_id).first()
            if not user and customer_id:
                user = User.query.filter_by(stripe_customer_id=customer_id).first()

            if user:
                user.is_premium = False
                user.plan = "free"
                user.stripe_subscription_id = None
                db.session.commit()

                send_telegram_message(
                    f"""
⚠️ <b>ABONNEMENT ANNULÉ</b>

👤 <b>Utilisateur :</b> {user.email}
🧾 <b>Subscription :</b> {subscription_id}
🔒 <b>Plan :</b> FREE
🔒 <b>Premium :</b> désactivé
""".strip()
                )

        elif event_type == "invoice.payment_succeeded":
            customer_id = data_object.get("customer")
            subscription_id = data_object.get("subscription")

            user = None
            if subscription_id:
                user = User.query.filter_by(stripe_subscription_id=subscription_id).first()
            if not user and customer_id:
                user = User.query.filter_by(stripe_customer_id=customer_id).first()

            if user:
                user.is_premium = True
                if user.plan == "free":
                    user.plan = "basic"
                if customer_id:
                    user.stripe_customer_id = customer_id
                if subscription_id:
                    user.stripe_subscription_id = subscription_id
                db.session.commit()

        elif event_type == "invoice.payment_failed":
            customer_id = data_object.get("customer")
            subscription_id = data_object.get("subscription")

            user = None
            if subscription_id:
                user = User.query.filter_by(stripe_subscription_id=subscription_id).first()
            if not user and customer_id:
                user = User.query.filter_by(stripe_customer_id=customer_id).first()

            if user:
                send_telegram_message(
                    f"""
❌ <b>PAIEMENT STRIPE ÉCHOUÉ</b>

👤 <b>Utilisateur :</b> {user.email}
💳 <b>Action recommandée :</b> vérifier la carte bancaire
""".strip()
                )

    except Exception as e:
        current_app.logger.error("Erreur traitement webhook Stripe: %s", repr(e))
        return "", 200

    return "", 200