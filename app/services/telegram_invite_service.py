import os
from datetime import datetime, timedelta, timezone

import requests
import config

from app.extensions import db
from app.models.telegram_invite import TelegramInvite


BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "") or ""
BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def _ensure_bot_token():
    if not BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN manquant")


def _chat_id_for_plan(plan: str) -> str:
    plan = (plan or "").strip().lower()

    if plan == "vip":
        return getattr(config, "TELEGRAM_VIP_CHAT_ID", "") or ""

    if plan == "premium":
        return getattr(config, "TELEGRAM_PREMIUM_CHAT_ID", "") or ""

    if plan == "basic":
        return getattr(config, "TELEGRAM_BASIC_CHAT_ID", "") or ""

    return ""


def _invite_name(plan: str, member_name: str = "") -> str:
    safe_plan = (plan or "member").strip().lower()
    safe_name = (member_name or "member").strip()
    return f"{safe_plan}:{safe_name}"[:32]


def _post_telegram(method: str, payload: dict) -> dict:
    _ensure_bot_token()

    response = requests.post(
        f"{BOT_API}/{method}",
        json=payload,
        timeout=20,
    )
    response.raise_for_status()

    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")

    return data.get("result", {})


def get_plan_chat_id(plan: str) -> str:
    return _chat_id_for_plan(plan)


def revoke_invite_link(chat_id: str, invite_link: str) -> dict:
    chat_id = str(chat_id or "").strip()
    invite_link = (invite_link or "").strip()

    if not chat_id:
        raise ValueError("chat_id manquant")

    if not invite_link:
        raise ValueError("invite_link manquant")

    payload = {
        "chat_id": chat_id,
        "invite_link": invite_link,
    }

    return _post_telegram("revokeChatInviteLink", payload)


def revoke_active_invites_for_user(user_id: int) -> int:
    """
    Révoque tous les anciens liens actifs d'un user en base + côté Telegram.
    """
    invites = (
        TelegramInvite.query
        .filter_by(user_id=user_id, is_revoked=False)
        .all()
    )

    revoked_count = 0

    for invite in invites:
        try:
            revoke_invite_link(invite.chat_id, invite.invite_link)
        except Exception:
            # Même si Telegram refuse ou que le lien est déjà mort,
            # on marque localement le lien comme révoqué.
            pass

        invite.is_revoked = True
        invite.revoked_at = datetime.utcnow()
        revoked_count += 1

    db.session.commit()
    return revoked_count


def create_secure_invite_link(plan: str, member_name: str = "", hours_valid: int = 2) -> dict:
    """
    Génère un lien sécurisé Telegram, sans enregistrement DB.
    - Basic/Premium: lien direct, 1 usage, expiration
    - VIP: join request
    """
    plan = (plan or "").strip().lower()
    chat_id = _chat_id_for_plan(plan)

    if not chat_id:
        raise ValueError(f"Chat ID manquant pour le plan: {plan}")

    if hours_valid <= 0:
        hours_valid = 2

    expire_date = int(
        (datetime.now(timezone.utc) + timedelta(hours=hours_valid)).timestamp()
    )

    is_vip = plan == "vip"

    payload = {
        "chat_id": chat_id,
        "name": _invite_name(plan, member_name),
        "expire_date": expire_date,
        "creates_join_request": is_vip,
    }

    if not is_vip:
        payload["member_limit"] = 1

    result = _post_telegram("createChatInviteLink", payload)
    result["chat_id"] = chat_id
    return result


def create_and_store_secure_invite_link(user, hours_valid: int = 2) -> TelegramInvite:
    """
    Révoque les anciens liens actifs du user, crée un nouveau lien Telegram,
    puis l'enregistre en base.
    """
    if not user:
        raise ValueError("user manquant")

    plan = str(getattr(user, "plan", "free") or "free").strip().lower()
    if plan not in {"basic", "premium", "vip"}:
        raise ValueError(f"Plan non autorisé pour invitation Telegram: {plan}")

    user_id = getattr(user, "id", None)
    if not user_id:
        raise ValueError("user.id manquant")

    member_name = getattr(user, "email", "") or f"user-{user_id}"

    # 1) Révoquer anciens liens actifs
    revoke_active_invites_for_user(user_id)

    # 2) Créer nouveau lien côté Telegram
    result = create_secure_invite_link(
        plan=plan,
        member_name=member_name,
        hours_valid=hours_valid,
    )

    invite_link = result.get("invite_link")
    chat_id = str(result.get("chat_id") or "")
    expire_ts = result.get("expire_date")

    expires_at = None
    if expire_ts:
        expires_at = datetime.fromtimestamp(expire_ts, tz=timezone.utc).replace(tzinfo=None)

    # 3) Sauvegarder en base
    invite = TelegramInvite(
        user_id=user_id,
        plan=plan,
        chat_id=chat_id,
        invite_link=invite_link,
        created_at=datetime.utcnow(),
        expires_at=expires_at,
        is_revoked=False,
        revoked_at=None,
        telegram_user_id=str(getattr(user, "telegram_user_id", "") or "") or None,
        note="generated_from_dashboard",
    )

    db.session.add(invite)
    db.session.commit()

    return invite


def get_latest_active_invite_for_user(user_id: int):
    return (
        TelegramInvite.query
        .filter_by(user_id=user_id, is_revoked=False)
        .order_by(TelegramInvite.created_at.desc())
        .first()
    )