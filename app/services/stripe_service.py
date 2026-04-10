import stripe
from flask import current_app

import config
from app.extensions import db

stripe.api_key = config.STRIPE_SECRET_KEY

PRICE_TO_PLAN = {
    config.STRIPE_PRICE_BASIC: "basic",
    config.STRIPE_PRICE_PREMIUM: "premium",
    config.STRIPE_PRICE_VIP: "vip",
}

PLAN_HIERARCHY = {
    "free": 0,
    "basic": 1,
    "premium": 2,
    "vip": 3,
}

PLAN_FEATURES = {
    "free": {
        "signals_limit": 5,
        "results_access": False,
        "signals_access": False,
        "briefing_access": False,
        "vip_access": False,
        "is_premium": False,
    },
    "basic": {
        "signals_limit": 20,
        "results_access": True,
        "signals_access": True,
        "briefing_access": False,
        "vip_access": False,
        "is_premium": True,
    },
    "premium": {
        "signals_limit": None,
        "results_access": True,
        "signals_access": True,
        "briefing_access": True,
        "vip_access": False,
        "is_premium": True,
    },
    "vip": {
        "signals_limit": None,
        "results_access": True,
        "signals_access": True,
        "briefing_access": True,
        "vip_access": True,
        "is_premium": True,
    },
}


def normalize_plan(plan: str) -> str:
    plan = (plan or "").strip().lower()
    if plan in ["basic", "premium", "vip"]:
        return plan
    return "free"


def get_price_id_for_plan(plan: str) -> str:
    plan = normalize_plan(plan)

    if plan == "basic":
        return config.STRIPE_PRICE_BASIC
    if plan == "premium":
        return config.STRIPE_PRICE_PREMIUM
    if plan == "vip":
        return config.STRIPE_PRICE_VIP

    return ""


def get_plan_from_price_id(price_id: str) -> str:
    return PRICE_TO_PLAN.get(price_id, "free")


def get_user_plan_key(user) -> str:
    return normalize_plan(getattr(user, "plan", "free"))


def get_plan_features(plan_or_user):
    if hasattr(plan_or_user, "plan"):
        plan_key = get_user_plan_key(plan_or_user)
    else:
        plan_key = normalize_plan(plan_or_user)

    return PLAN_FEATURES.get(plan_key, PLAN_FEATURES["free"])


def user_has_plan(user, required_plan: str) -> bool:
    current = PLAN_HIERARCHY.get(get_user_plan_key(user), 0)
    needed = PLAN_HIERARCHY.get(normalize_plan(required_plan), 0)
    return current >= needed


def get_subscription(subscription_id: str):
    if not subscription_id or not config.STRIPE_SECRET_KEY:
        return None

    try:
        return stripe.Subscription.retrieve(subscription_id)
    except Exception as e:
        current_app.logger.error("Erreur récupération abonnement Stripe: %s", repr(e))
        return None


def get_subscription_status(subscription_id: str):
    subscription = get_subscription(subscription_id)
    if not subscription:
        return None
    return subscription.get("status")


def get_subscription_price_id(subscription_id: str):
    subscription = get_subscription(subscription_id)
    if not subscription:
        return None

    items = subscription.get("items", {}).get("data", [])
    if not items:
        return None

    return items[0].get("price", {}).get("id")


def has_active_stripe_subscription(user) -> bool:
    if not user or not getattr(user, "stripe_subscription_id", None):
        return False

    status = get_subscription_status(user.stripe_subscription_id)
    return status in ["trialing", "active", "past_due"]


def sync_user_premium_status(user) -> None:
    """
    Synchronisation défensive depuis Stripe.
    Le webhook Stripe reste la source principale de vérité.
    """
    if not user:
        return

    if not getattr(user, "stripe_subscription_id", None):
        changed = False

        if getattr(user, "is_premium", False):
            user.is_premium = False
            changed = True

        if normalize_plan(getattr(user, "plan", "free")) != "free":
            user.plan = "free"
            changed = True

        if changed:
            db.session.commit()
            current_app.logger.info(
                "Utilisateur repassé en FREE (pas d'abonnement) : %s",
                getattr(user, "email", "unknown"),
            )
        return

    subscription = get_subscription(user.stripe_subscription_id)
    if not subscription:
        return

    status = subscription.get("status")
    items = subscription.get("items", {}).get("data", [])
    price_id = None

    if items:
        price_id = items[0].get("price", {}).get("id")

    resolved_plan = get_plan_from_price_id(price_id)
    is_active = status in ["trialing", "active", "past_due"]

    changed = False

    if is_active:
        if normalize_plan(getattr(user, "plan", "free")) != resolved_plan:
            user.plan = resolved_plan
            changed = True

        if not getattr(user, "is_premium", False):
            user.is_premium = True
            changed = True
    else:
        if normalize_plan(getattr(user, "plan", "free")) != "free":
            user.plan = "free"
            changed = True

        if getattr(user, "is_premium", False):
            user.is_premium = False
            changed = True

    customer_id = subscription.get("customer")
    if customer_id and getattr(user, "stripe_customer_id", None) != customer_id:
        user.stripe_customer_id = customer_id
        changed = True

    if changed:
        db.session.commit()
        current_app.logger.info(
            "Abonnement synchronisé | email=%s | plan=%s | active=%s",
            getattr(user, "email", "unknown"),
            user.plan,
            is_active,
        )