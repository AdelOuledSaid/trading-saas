import os

import requests
from flask import current_app

import config
from app.extensions import cache
from app.models import Signal


@cache.memoize(timeout=120)
def get_last_signal_minutes():
    """Minutes since the most recent non-deleted signal, or None if none exist."""
    from datetime import datetime

    last = (
        Signal.query
        .filter_by(is_deleted=False)
        .order_by(Signal.created_at.desc())
        .first()
    )
    if not last or not last.created_at:
        return None
    delta = datetime.utcnow() - last.created_at
    return max(int(delta.total_seconds() // 60), 0)


@cache.memoize(timeout=600)
def get_telegram_member_count():
    """Live public-channel subscriber count via the Telegram Bot API.

    Requires TELEGRAM_BOT_TOKEN and TELEGRAM_PUBLIC_CHAT_ID, and the bot must be
    a member/admin of the public channel. Falls back to the optional
    TELEGRAM_MEMBERS_FALLBACK env var, else returns None (counter is hidden).
    """
    token = (getattr(config, "TELEGRAM_BOT_TOKEN", "") or "").strip()
    chat_id = (getattr(config, "TELEGRAM_PUBLIC_CHAT_ID", "") or "").strip()

    if token and chat_id:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{token}/getChatMemberCount",
                params={"chat_id": chat_id},
                timeout=8,
            )
            data = r.json()
            if data.get("ok") and isinstance(data.get("result"), int):
                return data["result"]
            current_app.logger.warning("Telegram member count non-ok: %s", data)
        except Exception as exc:
            current_app.logger.warning("Telegram member count failed: %s", repr(exc))

    fallback = os.getenv("TELEGRAM_MEMBERS_FALLBACK", "").strip()
    if fallback.isdigit():
        return int(fallback)
    return None
