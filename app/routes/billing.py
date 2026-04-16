import stripe
from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_required, current_user

import config
from app.extensions import db
from app.services.telegram_service import send_telegram_message
from app.services.stripe_service import (
    normalize_plan,
    get_price_id_for_plan,
    sync_user_premium_status,
    has_active_stripe_subscription,
    get_subscription_status,
)
from app.services.email_service import send_email
billing_bp = Blueprint("billing", __name__)
stripe.api_key = config.STRIPE_SECRET_KEY

ALLOWED_PLANS = ["basic", "premium", "vip"]


@billing_bp.route("/<lang_code>/pricing")
def pricing(lang_code):
    if current_user.is_authenticated:
        sync_user_premium_status(current_user)
        user_plan = normalize_plan(getattr(current_user, "plan", "free"))
        subscription_status = get_subscription_status(
            getattr(current_user, "stripe_subscription_id", None)
        )
    else:
        user_plan = "free"
        subscription_status = None

    return render_template(
        "pricing.html",
        stripe_publishable_key=config.STRIPE_PUBLISHABLE_KEY,
        user_plan=user_plan,
        subscription_status=subscription_status,
    )


@billing_bp.route("/<lang_code>/create-checkout-session", methods=["POST"])
@login_required
def create_checkout_session(lang_code):
    selected_plan = normalize_plan(request.form.get("plan"))

    if selected_plan not in ALLOWED_PLANS:
        flash("Plan invalide.", "danger")
        return redirect(url_for("billing.pricing", lang_code=lang_code))

    price_id = get_price_id_for_plan(selected_plan, lang_code)
    if not price_id:
        flash("Le plan sélectionné n'est pas configuré correctement.", "warning")
        return redirect(url_for("billing.pricing", lang_code=lang_code))

    if not config.STRIPE_SECRET_KEY:
        flash("Stripe n'est pas configuré correctement.", "danger")
        return redirect(url_for("billing.pricing", lang_code=lang_code))

    status = get_subscription_status(getattr(current_user, "stripe_subscription_id", None))
    if status in ["active", "trialing"]:
        flash("Un abonnement actif existe déjà sur votre compte.", "warning")
        return redirect(url_for("billing.pricing", lang_code=lang_code))

    if has_active_stripe_subscription(current_user):
        flash("Un abonnement actif existe déjà sur votre compte.", "warning")
        return redirect(url_for("billing.pricing", lang_code=lang_code))

    try:
        if not current_user.stripe_customer_id:
            customer = stripe.Customer.create(email=current_user.email)
            current_user.stripe_customer_id = customer["id"]
            db.session.commit()
            current_app.logger.info(
                "Nouveau client Stripe créé : %s",
                current_user.stripe_customer_id
            )

        checkout_session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            customer=current_user.stripe_customer_id,
            client_reference_id=str(current_user.id),
            metadata={
                "user_id": str(current_user.id),
                "user_email": current_user.email,
                "plan": selected_plan,
                "source": "pricing",
                "lang_code": lang_code,
            },
            subscription_data={
                "metadata": {
                    "user_id": str(current_user.id),
                    "user_email": current_user.email,
                    "plan": selected_plan,
                    "source": "pricing",
                    "lang_code": lang_code,
                }
            },
            success_url=f"{config.DOMAIN}/{lang_code}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{config.DOMAIN}/{lang_code}/cancel",
        )

        return redirect(checkout_session.url, code=303)

    except Exception as e:
        current_app.logger.error("Erreur Stripe create_checkout_session: %s", repr(e))
        flash("Impossible de créer la session de paiement.", "danger")
        return redirect(url_for("billing.pricing", lang_code=lang_code))


@billing_bp.route("/<lang_code>/create-customer-portal-session", methods=["POST"])
@login_required
def create_customer_portal_session(lang_code):
    if not current_user.stripe_customer_id:
        flash("Aucun client Stripe lié à ce compte.", "warning")
        return redirect(url_for("billing.pricing", lang_code=lang_code))

    if not config.STRIPE_SECRET_KEY:
        flash("Stripe n'est pas configuré correctement.", "danger")
        return redirect(url_for("billing.pricing", lang_code=lang_code))

    try:
        portal_session = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url=f"{config.DOMAIN}/{lang_code}/pricing"
        )
        return redirect(portal_session.url, code=303)

    except Exception as e:
        current_app.logger.error("Erreur Stripe customer portal: %s", repr(e))
        flash("Impossible d'ouvrir le portail client.", "danger")
        return redirect(url_for("billing.pricing", lang_code=lang_code))


@billing_bp.route("/<lang_code>/success")
@login_required
def success(lang_code):
    session_id = request.args.get("session_id")
    session_data = None
    vip_link = None

    if session_id and config.STRIPE_SECRET_KEY:
        try:
            session_data = stripe.checkout.Session.retrieve(session_id)

            customer_id = session_data.get("customer")
            subscription_id = session_data.get("subscription")

            if customer_id and not current_user.stripe_customer_id:
                current_user.stripe_customer_id = customer_id

            if subscription_id and not current_user.stripe_subscription_id:
                current_user.stripe_subscription_id = subscription_id

            db.session.commit()

            sync_user_premium_status(current_user)

            try:
                html = f"""
                <div style="background:#0b0f1a;padding:30px;color:white;font-family:Arial,sans-serif;">
                    <h2 style="color:#00ff99;">Paiement confirmé 💰</h2>
                    <p>Merci pour ton abonnement VelWolef.</p>
                    <p><strong>Plan :</strong> {current_user.plan}</p>
                    <p><strong>Email :</strong> {current_user.email}</p>
                    <p style="margin-top:20px;color:#aaaaaa;font-size:12px;">
                        Ton accès premium a bien été mis à jour.
                    </p>
                </div>
                """

                send_email(
                    current_user.email,
                    "Paiement confirmé VelWolef",
                    html
                )
            except Exception as e:
                current_app.logger.warning(f"Erreur email paiement: {e}")

            try:
                plan_name = normalize_plan(getattr(current_user, "plan", "free"))
                if plan_name in ["basic", "premium", "vip"]:
                    send_telegram_message(
                        f"✅ Nouveau paiement confirmé sur VelWolef\n"
                        f"Utilisateur: {current_user.email}\n"
                        f"Plan: {plan_name}\n"
                        f"Langue: {lang_code}"
                    )
            except Exception as telegram_error:
                current_app.logger.warning(
                    "Erreur notification Telegram paiement: %s",
                    repr(telegram_error)
                )

        except Exception as e:
            current_app.logger.error("Erreur récupération session Stripe: %s", repr(e))

    if (getattr(current_user, "plan", "") or "").lower() == "vip" and getattr(config, "TELEGRAM_VIP_INVITE_LINK", None):
        vip_link = config.TELEGRAM_VIP_INVITE_LINK

    return render_template(
        "success.html",
        session_data=session_data,
        vip_link=vip_link,
    )


@billing_bp.route("/<lang_code>/cancel")
@login_required
def cancel(lang_code):
    return render_template("cancel.html")