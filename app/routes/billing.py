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

billing_bp = Blueprint("billing", __name__)
stripe.api_key = config.STRIPE_SECRET_KEY


@billing_bp.route("/pricing")
def pricing():
    if current_user.is_authenticated:
        sync_user_premium_status(current_user)
        user_plan = normalize_plan(current_user.plan)
    else:
        user_plan = "free"

    return render_template(
        "pricing.html",
        stripe_publishable_key=config.STRIPE_PUBLISHABLE_KEY,
        user_plan=user_plan
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
            current_app.logger.info(
                "Nouveau client Stripe créé : %s",
                current_user.stripe_customer_id
            )

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
            subscription_data={
                "metadata": {
                    "user_id": str(current_user.id),
                    "user_email": current_user.email,
                    "plan": selected_plan,
                }
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

            if customer_id and not current_user.stripe_customer_id:
                current_user.stripe_customer_id = customer_id

            if subscription_id and not current_user.stripe_subscription_id:
                current_user.stripe_subscription_id = subscription_id

            db.session.commit()

            # Synchronisation défensive depuis Stripe
            sync_user_premium_status(current_user)

        except Exception as e:
            current_app.logger.error("Erreur récupération session Stripe: %s", repr(e))

    if (current_user.plan or "").lower() == "vip" and config.TELEGRAM_VIP_INVITE_LINK:
        vip_link = config.TELEGRAM_VIP_INVITE_LINK

    return render_template(
        "success.html",
        session_data=session_data,
        vip_link=vip_link
    )


@billing_bp.route("/cancel")
@login_required
def cancel():
    return render_template("cancel.html")