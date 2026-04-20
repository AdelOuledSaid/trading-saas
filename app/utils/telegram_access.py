import config


def get_telegram_invite_link(plan: str) -> str:
    plan = str(plan or "").strip().lower()

    if plan == "vip":
        return getattr(config, "TELEGRAM_VIP_INVITE_LINK", "") or ""

    if plan == "premium":
        return getattr(config, "TELEGRAM_PREMIUM_INVITE_LINK", "") or ""

    if plan == "basic":
        return getattr(config, "TELEGRAM_BASIC_INVITE_LINK", "") or ""

    return ""
def user_has_telegram_access(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False

    plan = str(getattr(user, "plan", "") or "").strip().lower()
    return plan in {"basic", "premium", "vip"}
def get_user_telegram_link(user) -> str:
    if not user_has_telegram_access(user):
        return ""

    plan = str(getattr(user, "plan", "") or "").strip().lower()
    return get_telegram_invite_link(plan)