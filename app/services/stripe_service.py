import stripe
from flask import current_app

import config
from app.extensions import db

stripe.api_key = config.STRIPE_SECRET_KEY

# 🔥 MULTI PRICE SUPPORT
PRICE_TO_PLAN = {
    # BASIC
    config.STRIPE_PRICE_BASIC_EUR: "basic",
    config.STRIPE_PRICE_BASIC_USD: "basic",

    # PREMIUM
    config.STRIPE_PRICE_PREMIUM_EUR: "premium",
    config.STRIPE_PRICE_PREMIUM_USD: "premium",

    # VIP
    config.STRIPE_PRICE_VIP_EUR: "vip",
    config.STRIPE_PRICE_VIP_USD: "vip",
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


# 🔥 MODIFIÉ
def get_price_id_for_plan(plan: str, lang_code: str) -> str:
    plan = normalize_plan(plan)
    is_us = lang_code == "en"

    if plan == "basic":
        return config.STRIPE_PRICE_BASIC_USD if is_us else config.STRIPE_PRICE_BASIC_EUR

    if plan == "premium":
        return config.STRIPE_PRICE_PREMIUM_USD if is_us else config.STRIPE_PRICE_PREMIUM_EUR

    if plan == "vip":
        return config.STRIPE_PRICE_VIP_USD if is_us else config.STRIPE_PRICE_VIP_EUR

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
        current_app.logger.error("Erreur Stripe: %s", repr(e))
        return None


def get_subscription_status(subscription_id: str):
    sub = get_subscription(subscription_id)
    return sub.get("status") if sub else None


def get_subscription_price_id(subscription_id: str):
    sub = get_subscription(subscription_id)
    if not sub:
        return None

    items = sub.get("items", {}).get("data", [])
    if not items:
        return None

    return items[0].get("price", {}).get("id")


def has_active_stripe_subscription(user) -> bool:
    if not user or not getattr(user, "stripe_subscription_id", None):
        return False

    status = get_subscription_status(user.stripe_subscription_id)
    return status in ["trialing", "active", "past_due"]


def sync_user_premium_status(user):
    if not user:
        return

    if not getattr(user, "stripe_subscription_id", None):
        user.plan = "free"
        user.is_premium = False
        db.session.commit()
        return

    sub = get_subscription(user.stripe_subscription_id)
    if not sub:
        return

    status = sub.get("status")
    price_id = get_subscription_price_id(user.stripe_subscription_id)

    plan = get_plan_from_price_id(price_id)
    active = status in ["trialing", "active", "past_due"]

    if active:
        user.plan = plan
        user.is_premium = True
    else:
        user.plan = "free"
        user.is_premium = False

    db.session.commit()