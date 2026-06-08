import stripe
from flask import Blueprint, request, jsonify, current_app

import config
from app.extensions import db
from app.models import User
from app.services.stripe_service import get_plan_from_price_id

stripe.api_key = config.STRIPE_SECRET_KEY

stripe_webhook_bp = Blueprint("stripe_webhook", __name__)


def _stripe_get(obj, key, default=None):
    """Compatible avec les objets Stripe v15 (StripeObject) et les dicts."""
    try:
        if hasattr(obj, key):
            val = getattr(obj, key)
            return val if val is not None else default
        return obj[key]
    except (KeyError, AttributeError, TypeError):
        return default


def _get_user_from_customer_or_metadata(obj):
    metadata = _stripe_get(obj, "metadata") or {}
    # metadata peut être un StripeObject aussi
    if hasattr(metadata, "get"):
        user_id = metadata.get("user_id") if hasattr(metadata, "get") else _stripe_get(metadata, "user_id")
    else:
        user_id = _stripe_get(metadata, "user_id")

    if user_id:
        try:
            user = User.query.get(int(user_id))
            if user:
                return user
        except Exception:
            pass

    customer_id = _stripe_get(obj, "customer")
    if customer_id:
        return User.query.filter_by(stripe_customer_id=customer_id).first()

    return None


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
            metadata = _stripe_get(obj, "metadata") or {}
            user_id = metadata.get("user_id") if hasattr(metadata, "get") else _stripe_get(metadata, "user_id")
            customer_id = _stripe_get(obj, "customer")
            subscription_id = _stripe_get(obj, "subscription")

            if user_id:
                try:
                    user = User.query.get(int(user_id))
                except Exception:
                    user = None

                if user:
                    if customer_id:
                        user.stripe_customer_id = customer_id
                    if subscription_id:
                        user.stripe_subscription_id = subscription_id
                    db.session.commit()

    elif event_type in ["customer.subscription.created", "customer.subscription.updated"]:
        subscription = obj
        user = _get_user_from_customer_or_metadata(subscription)

        if user:
            items_obj = _stripe_get(subscription, "items") or {}; items = (items_obj.get("data", []) if hasattr(items_obj, "get") else getattr(items_obj, "data", []))
            price_id = None

            if items:
                price_id = (_stripe_get(items[0], "price") or {}).get("id") if hasattr(_stripe_get(items[0], "price"), "get") else _stripe_get(_stripe_get(items[0], "price"), "id")

            plan = get_plan_from_price_id(price_id)
            status = _stripe_get(subscription, "status")

            active_statuses = ["trialing", "active"]

            user.stripe_customer_id = _stripe_get(subscription, "customer")
            user.stripe_subscription_id = _stripe_get(subscription, "id")

            if status in active_statuses:
                user.plan = plan
                user.is_premium = plan in ["basic", "premium", "vip", "pro"]
            else:
                user.plan = "free"
                user.is_premium = False

            db.session.commit()

    elif event_type in [
        "customer.subscription.deleted",
        "customer.subscription.paused",
        "customer.subscription.unpaid",
    ]:
        subscription = obj
        user = _get_user_from_customer_or_metadata(subscription)

        if user:
            user.plan = "free"
            user.is_premium = False
            user.stripe_customer_id = _stripe_get(subscription, "customer") or user.stripe_customer_id
            user.stripe_subscription_id = _stripe_get(subscription, "id") or user.stripe_subscription_id
            db.session.commit()

    return jsonify({"received": True}), 200