from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from app.models import User
from app.extensions import db

from app.services.telegram_invite_service import create_and_store_secure_invite_link

telegram_bp = Blueprint("telegram", __name__)


@telegram_bp.route("/telegram/link-account", methods=["POST"])
def link_telegram_account():
    data = request.get_json(silent=True) or {}

    token = (data.get("token") or "").strip()
    telegram_user_id = str(data.get("telegram_user_id") or "").strip()
    telegram_username = (data.get("telegram_username") or "").strip()
    first_name = (data.get("first_name") or "").strip()
    last_name = (data.get("last_name") or "").strip()

    if not token or not telegram_user_id:
        return jsonify({
            "ok": False,
            "error": "missing_data"
        }), 400

    user = User.query.filter_by(telegram_link_token=token).first()

    if not user:
        return jsonify({
            "ok": False,
            "error": "invalid_or_expired_token"
        }), 404

    # Empêche de lier le même compte Telegram à plusieurs users
    existing_user = User.query.filter_by(telegram_user_id=telegram_user_id).first()
    if existing_user and existing_user.id != user.id:
        return jsonify({
            "ok": False,
            "error": "telegram_account_already_linked"
        }), 409

    user.telegram_user_id = telegram_user_id
    user.telegram_username = telegram_username or None
    user.telegram_verified_at = datetime.utcnow()

    # Token usage unique
    user.telegram_link_token = None

    db.session.commit()

    display_name = " ".join(part for part in [first_name, last_name] if part).strip()

    return jsonify({
        "ok": True,
        "message": "telegram_linked",
        "plan": user.plan,
        "email": user.email,
        "telegram_user_id": user.telegram_user_id,
        "telegram_username": user.telegram_username,
        "display_name": display_name,
    }), 200


@telegram_bp.route("/telegram/generate-invite", methods=["POST"])
@login_required
def generate_telegram_invite():
    plan = str(getattr(current_user, "plan", "free") or "free").strip().lower()

    if plan not in {"basic", "premium", "vip"}:
        return jsonify({
            "ok": False,
            "error": "plan_not_allowed"
        }), 403

    if not getattr(current_user, "telegram_user_id", None):
        return jsonify({
            "ok": False,
            "error": "telegram_not_linked"
        }), 400

    try:
        invite = create_and_store_secure_invite_link(
            user=current_user,
            hours_valid=2,
        )

        return jsonify({
            "ok": True,
            "invite_id": invite.id,
            "invite_link": invite.invite_link,
            "expire_date": invite.expires_at.isoformat() if invite.expires_at else None,
            "creates_join_request": plan == "vip",
        }), 200

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": "invite_generation_failed",
            "details": str(e),
        }), 500