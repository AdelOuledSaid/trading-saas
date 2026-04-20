from flask import Blueprint, request, jsonify, current_app
from app.models.telegram_invite import TelegramInvite
from app.extensions import db
import requests
import os

telegram_webhook_bp = Blueprint("telegram_webhook", __name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "") or ""
BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

APP_BASE_URL = (
    os.getenv("APP_BASE_URL", "").rstrip("/")
    or os.getenv("SITE_URL", "").rstrip("/")
    or "http://127.0.0.1:5000"
)


def _send_bot_message(chat_id: str | int, text: str) -> None:
    if not BOT_TOKEN or not chat_id or not text:
        return

    try:
        response = requests.post(
            f"{BOT_API}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
            },
            timeout=20,
        )
        response.raise_for_status()
    except Exception as e:
        current_app.logger.warning("Telegram sendMessage error: %s", e)


def approve_request(chat_id: str | int, user_id: str | int) -> None:
    response = requests.post(
        f"{BOT_API}/approveChatJoinRequest",
        json={
            "chat_id": int(chat_id),
            "user_id": int(user_id),
        },
        timeout=20,
    )
    response.raise_for_status()


def decline_request(chat_id: str | int, user_id: str | int) -> None:
    response = requests.post(
        f"{BOT_API}/declineChatJoinRequest",
        json={
            "chat_id": int(chat_id),
            "user_id": int(user_id),
        },
        timeout=20,
    )
    response.raise_for_status()


def _handle_start_command(message: dict) -> None:
    text = str(message.get("text", "") or "").strip()
    if not text.startswith("/start"):
        return

    from_user = message.get("from", {}) or {}
    chat = message.get("chat", {}) or {}

    telegram_user_id = str(from_user.get("id", "") or "").strip()
    telegram_username = str(from_user.get("username", "") or "").strip()
    first_name = str(from_user.get("first_name", "") or "").strip()
    last_name = str(from_user.get("last_name", "") or "").strip()
    chat_id = chat.get("id")

    parts = text.split(maxsplit=1)
    token = parts[1].strip() if len(parts) > 1 else ""

    current_app.logger.info(
        "Telegram /start reçu | tg_user=%s | username=%s | has_token=%s",
        telegram_user_id,
        telegram_username,
        bool(token),
    )

    if not telegram_user_id:
        return

    if not token:
        _send_bot_message(
            chat_id,
            "Bienvenue. Ouvre d'abord le lien de connexion Telegram depuis ton dashboard.",
        )
        return

    payload = {
        "token": token,
        "telegram_user_id": telegram_user_id,
        "telegram_username": telegram_username,
        "first_name": first_name,
        "last_name": last_name,
    }

    try:
        response = requests.post(
            f"{APP_BASE_URL}/telegram/link-account",
            json=payload,
            timeout=20,
        )

        current_app.logger.info(
            "Backend /telegram/link-account | status=%s | body=%s",
            response.status_code,
            response.text,
        )

        if response.status_code == 200:
            data = response.json()
            plan = str(data.get("plan", "free") or "free").upper()

            _send_bot_message(
                chat_id,
                f"✅ Ton compte Telegram est maintenant lié.\n"
                f"Plan détecté : {plan}\n"
                f"Retourne sur ton dashboard pour continuer.",
            )
        elif response.status_code == 409:
            _send_bot_message(
                chat_id,
                "❌ Ce compte Telegram est déjà lié à un autre utilisateur.",
            )
        else:
            _send_bot_message(
                chat_id,
                "❌ Lien invalide ou expiré. Retourne sur ton dashboard et regénère le lien.",
            )

    except Exception as e:
        current_app.logger.warning("Erreur POST /telegram/link-account: %s", e)
        _send_bot_message(
            chat_id,
            "❌ Erreur de connexion avec le site. Réessaie dans quelques instants.",
        )


def _handle_join_request(join: dict) -> None:
    from_user = join.get("from", {}) or {}
    chat = join.get("chat", {}) or {}
    invite_link_data = join.get("invite_link", {}) or {}

    telegram_user_id = str(from_user.get("id", "") or "").strip()
    chat_id = str(chat.get("id", "") or "").strip()
    invite_link = str(invite_link_data.get("invite_link", "") or "").strip()

    current_app.logger.info(
        "chat_join_request reçu | tg_user=%s | chat_id=%s | has_invite_link=%s",
        telegram_user_id,
        chat_id,
        bool(invite_link),
    )

    if not telegram_user_id or not chat_id:
        current_app.logger.warning("Join request invalide")
        return

    invite = None

    if invite_link:
        invite = (
            TelegramInvite.query
            .filter_by(
                invite_link=invite_link,
                chat_id=chat_id,
                is_revoked=False,
            )
            .order_by(TelegramInvite.created_at.desc())
            .first()
        )

    if not invite:
        invite = (
            TelegramInvite.query
            .filter_by(
                telegram_user_id=telegram_user_id,
                chat_id=chat_id,
                is_revoked=False,
            )
            .order_by(TelegramInvite.created_at.desc())
            .first()
        )

    if not invite:
        current_app.logger.warning(
            "Join refusé | aucun invite trouvé | tg_user=%s | chat_id=%s",
            telegram_user_id,
            chat_id,
        )
        decline_request(chat_id, telegram_user_id)
        return

    if invite.is_expired:
        current_app.logger.warning(
            "Join refusé | invite expiré | invite_id=%s | tg_user=%s",
            invite.id,
            telegram_user_id,
        )
        invite.is_revoked = True
        db.session.commit()
        decline_request(chat_id, telegram_user_id)
        return

    if invite.telegram_user_id and invite.telegram_user_id != telegram_user_id:
        current_app.logger.warning(
            "Join refusé | mismatch tg_user | invite_id=%s | expected=%s | got=%s",
            invite.id,
            invite.telegram_user_id,
            telegram_user_id,
        )
        decline_request(chat_id, telegram_user_id)
        return

    try:
        approve_request(chat_id, telegram_user_id)
        invite.note = "approved"
        db.session.commit()

        current_app.logger.info(
            "Join accepté | invite_id=%s | tg_user=%s | chat_id=%s",
            invite.id,
            telegram_user_id,
            chat_id,
        )
    except Exception as e:
        current_app.logger.warning("Erreur approveChatJoinRequest: %s", e)
        decline_request(chat_id, telegram_user_id)


@telegram_webhook_bp.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json(silent=True) or {}

    current_app.logger.info("Telegram webhook reçu: %s", data)

    try:
        if "message" in data:
            _handle_start_command(data["message"])

        if "chat_join_request" in data:
            _handle_join_request(data["chat_join_request"])

        return jsonify({"ok": True}), 200

    except Exception as e:
        current_app.logger.exception("Telegram webhook error: %s", e)
        return jsonify({"ok": False, "error": "internal_error"}), 500