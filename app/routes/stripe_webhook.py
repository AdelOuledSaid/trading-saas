import stripe
from flask import Blueprint, request, jsonify, current_app

import config
from app.extensions import db
from app.models import User
from app.services.stripe_service import get_plan_from_price_id, normalize_plan

stripe.api_key = config.STRIPE_SECRET_KEY

stripe_webhook_bp = Blueprint("stripe_webhook", __name__)


def _stripe_get(obj, key, default=None):
    try:
        if hasattr(obj, key):
            value = getattr(obj, key)
            return value if value is not None else default
        return obj[key]
    except Exception:
        return default


def _get_metadata_value(obj, key, default=None):
    metadata = _stripe_get(obj, "metadata") or {}

    try:
        if hasattr(metadata, "get"):
            return metadata.get(key, default)
        return metadata[key]
    except Exception:
        return default


def _get_user_from_customer_or_metadata(obj):
    user_id = _get_metadata_value(obj, "user_id")
    customer_id = _stripe_get(obj, "customer")

    if user_id:
        try:
            user = User.query.get(int(user_id))
            if user:
                return user
        except Exception:
            current_app.logger.warning("Stripe webhook: user_id invalide: %s", user_id)

    if customer_id:
        return User.query.filter_by(stripe_customer_id=customer_id).first()

    return None


def _get_subscription_price_id(subscription):
    items_obj = _stripe_get(subscription, "items") or {}
    items = _stripe_get(items_obj, "data", [])

    if not items:
        return None

    first_item = items[0]
    price_obj = _stripe_get(first_item, "price") or {}

    return _stripe_get(price_obj, "id")


def _get_plan_from_subscription(subscription):
    # Priorité au plan envoyé dans subscription_data.metadata depuis billing.py
    plan = (_get_metadata_value(subscription, "plan", "") or "").lower().strip()

    if plan in ["basic", "premium", "vip"]:
        return plan

    # Fallback : retrouver le plan depuis le Price ID
    price_id = _get_subscription_price_id(subscription)
    return normalize_plan(get_plan_from_price_id(price_id))


def _activate_user_subscription(user, subscription):
    status = _stripe_get(subscription, "status")
    plan = _get_plan_from_subscription(subscription)

    customer_id = _stripe_get(subscription, "customer")
    subscription_id = _stripe_get(subscription, "id")

    if customer_id:
        user.stripe_customer_id = customer_id

    if subscription_id:
        user.stripe_subscription_id = subscription_id

    if status in ["trialing", "active", "past_due"] and plan in ["basic", "premium", "vip"]:
        user.plan = plan
        user.is_premium = True
    else:
        user.plan = "free"
        user.is_premium = False

    db.session.commit()

    current_app.logger.info(
        "Stripe subscription sync: user=%s plan=%s premium=%s status=%s sub=%s",
        getattr(user, "email", None),
        user.plan,
        user.is_premium,
        status,
        subscription_id,
    )


def _deactivate_user_subscription(user, subscription=None):
    user.plan = "free"
    user.is_premium = False

    if subscription is not None:
        customer_id = _stripe_get(subscription, "customer")
        subscription_id = _stripe_get(subscription, "id")

        if customer_id:
            user.stripe_customer_id = customer_id

        if subscription_id:
            user.stripe_subscription_id = subscription_id

    db.session.commit()

    current_app.logger.info(
        "Stripe subscription deactivated: user=%s",
        getattr(user, "email", None),
    )


@stripe_webhook_bp.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            config.STRIPE_WEBHOOK_SECRET,
        )
    except ValueError:
        current_app.logger.warning("Stripe webhook: payload invalide")
        return jsonify({"error": "payload invalide"}), 400
    except stripe.error.SignatureVerificationError:
        current_app.logger.warning("Stripe webhook: signature invalide")
        return jsonify({"error": "signature invalide"}), 400

    event_type = event["type"]
    obj = event["data"]["object"]

    current_app.logger.info("Stripe webhook reçu: %s", event_type)

    if event_type == "checkout.session.completed":
        if _stripe_get(obj, "mode") == "subscription":
            user_id = _get_metadata_value(obj, "user_id")
            customer_id = _stripe_get(obj, "customer")
            subscription_id = _stripe_get(obj, "subscription")

            user = None

            if user_id:
                try:
                    user = User.query.get(int(user_id))
                except Exception:
                    user = None

            if not user and customer_id:
                user = User.query.filter_by(stripe_customer_id=customer_id).first()

            if not user:
                current_app.logger.warning(
                    "Stripe checkout.session.completed: utilisateur introuvable customer=%s user_id=%s",
                    customer_id,
                    user_id,
                )
                return jsonify({"received": True, "warning": "user_not_found"}), 200

            if customer_id:
                user.stripe_customer_id = customer_id

            if subscription_id:
                user.stripe_subscription_id = subscription_id

                try:
                    subscription = stripe.Subscription.retrieve(subscription_id)
                    _activate_user_subscription(user, subscription)
                except Exception as e:
                    current_app.logger.error(
                        "Stripe checkout.session.completed: erreur retrieve subscription %s",
                        repr(e),
                    )
                    db.session.commit()
            else:
                db.session.commit()

    elif event_type in ["customer.subscription.created", "customer.subscription.updated"]:
        subscription = obj
        user = _get_user_from_customer_or_metadata(subscription)

        if not user:
            current_app.logger.warning(
                "Stripe subscription event: utilisateur introuvable customer=%s sub=%s",
                _stripe_get(subscription, "customer"),
                _stripe_get(subscription, "id"),
            )
            return jsonify({"received": True, "warning": "user_not_found"}), 200

        _activate_user_subscription(user, subscription)

    elif event_type in [
        "customer.subscription.deleted",
        "customer.subscription.paused",
        "customer.subscription.unpaid",
    ]:
        subscription = obj
        user = _get_user_from_customer_or_metadata(subscription)

        if not user:
            current_app.logger.warning(
                "Stripe subscription deleted/paused: utilisateur introuvable customer=%s sub=%s",
                _stripe_get(subscription, "customer"),
                _stripe_get(subscription, "id"),
            )
            return jsonify({"received": True, "warning": "user_not_found"}), 200

        _deactivate_user_subscription(user, subscription)

    elif event_type == "invoice.payment_succeeded":
        invoice = obj
        subscription_id = _stripe_get(invoice, "subscription")
        customer_id = _stripe_get(invoice, "customer")

        if subscription_id:
            try:
                subscription = stripe.Subscription.retrieve(subscription_id)
                user = _get_user_from_customer_or_metadata(subscription)

                if not user and customer_id:
                    user = User.query.filter_by(stripe_customer_id=customer_id).first()

                if user:
                    _activate_user_subscription(user, subscription)
            except Exception as e:
                current_app.logger.error(
                    "Stripe invoice.payment_succeeded: erreur sync %s",
                    repr(e),
                )

    elif event_type == "invoice.payment_failed":
        invoice = obj
        customer_id = _stripe_get(invoice, "customer")

        if customer_id:
            user = User.query.filter_by(stripe_customer_id=customer_id).first()
            if user:
                user.plan = "free"
                user.is_premium = False
                db.session.commit()

    return jsonify({"received": True}), 200