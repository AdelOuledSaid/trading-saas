from functools import wraps
from flask import abort
from flask_login import current_user

PLAN_LEVELS = {
    "free": 0,
    "basic": 1,
    "premium": 2,
    "vip": 3
}

FEATURES = {
    # Basic
    "morning_brief": "basic",
    "daily_news": "basic",
    "basic_signals": "basic",
    "basic_dashboard": "basic",

    # Premium
    "premium_brief_2": "premium",
    "second_brief": "premium",
    "premium_news": "premium",
    "trade_explanations": "premium",
    "trade_replays": "premium",
    "advanced_stats": "premium",
    "mini_courses": "premium",
    "full_history": "premium",
    "premium_signals": "premium",

    # VIP
    "vip_briefings": "vip",
    "vip_live_opportunities": "vip",
    "vip_instant_news": "vip",
    "vip_unlimited_signals": "vip",
    "vip_detailed_tp_sl": "vip",
    "vip_private_telegram": "vip",
    "vip_advanced_courses": "vip",
    "vip_replays": "vip"
}


def get_plan_level(plan_name: str) -> int:
    return PLAN_LEVELS.get((plan_name or "free").lower(), 0)


def has_access(user_plan: str, feature_name: str) -> bool:
    required_plan = FEATURES.get(feature_name)
    if not required_plan:
        return False
    return get_plan_level(user_plan) >= get_plan_level(required_plan)


def signal_limit_for_plan(plan_name: str) -> int:
    limits = {
        "free": 0,
        "basic": 5,
        "premium": 10,
        "vip": 999999
    }
    return limits.get((plan_name or "free").lower(), 0)


def plan_required(required_plan: str):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            user_plan = getattr(current_user, "plan", "free")
            if get_plan_level(user_plan) < get_plan_level(required_plan):
                abort(403)
            return view_func(*args, **kwargs)
        return wrapped
    return decorator


def feature_required(feature_name: str):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            user_plan = getattr(current_user, "plan", "free")
            if not has_access(user_plan, feature_name):
                abort(403)
            return view_func(*args, **kwargs)
        return wrapped
    return decorator