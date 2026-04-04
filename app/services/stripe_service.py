import stripe
from flask import current_app
from app.extensions import db
import config

stripe.api_key = config.STRIPE_SECRET_KEY


def get_price_id_for_plan(plan: str) -> str:
    plan = (plan or "").strip().lower()

    if plan == "basic":
        return config.STRIPE_PRICE_BASIC
    if plan == "premium":
        return config.STRIPE_PRICE_PREMIUM
    if plan == "vip":
        return config.STRIPE_PRICE_VIP

    return ""


def normalize_plan(plan: str) -> str:
    plan = (plan or "").strip().lower()
    if plan in ["basic", "premium", "vip"]:
        return plan
    return "free"


def user_has_plan(user, required_plan: str) -> bool:
    hierarchy = {
        "free": 0,
        "basic": 1,
        "premium": 2,
        "vip": 3,
    }
    current = hierarchy.get((user.plan or "free").lower(), 0)
    needed = hierarchy.get(required_plan.lower(), 0)
    return current >= needed


def get_subscription_status(subscription_id: str):
    if not subscription_id or not config.STRIPE_SECRET_KEY:
        return None

    try:
        subscription = stripe.Subscription.retrieve(subscription_id)
        return subscription.get("status")
    except Exception as e:
        current_app.logger.error("Erreur récupération abonnement Stripe: %s", repr(e))
        return None


def has_active_stripe_subscription(user) -> bool:
    if not user or not user.stripe_subscription_id:
        return False

    status = get_subscription_status(user.stripe_subscription_id)
    return status in ["trialing", "active", "past_due"]


def sync_user_premium_status(user) -> None:
    if not user:
        return

    active = has_active_stripe_subscription(user)

    if active:
        changed = False

        if not user.is_premium:
            user.is_premium = True
            changed = True

        if (user.plan or "free") == "free":
            user.plan = "basic"
            changed = True

        if changed:
            db.session.commit()
            current_app.logger.info("Premium synchronisé à TRUE pour %s", user.email)
    else:
        if user.is_premium and user.stripe_subscription_id:
            user.is_premium = False
            user.plan = "free"
            db.session.commit()
            current_app.logger.info("Premium synchronisé à FALSE pour %s", user.email)