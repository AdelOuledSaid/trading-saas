import secrets
from datetime import datetime
from flask import current_app
from app.extensions import db


# =====================================================
# TOKEN GENERATION
# =====================================================

def generate_telegram_link_token() -> str:
    """
    Génère un token sécurisé unique pour lier un compte Telegram
    """
    return secrets.token_urlsafe(32)


# =====================================================
# TOKEN MANAGEMENT
# =====================================================

def ensure_telegram_link_token(user) -> str:
    """
    Génère un token si l'utilisateur n'en a pas encore
    """
    if not user.telegram_link_token:
        user.telegram_link_token = generate_telegram_link_token()
        db.session.commit()

    return user.telegram_link_token


def reset_telegram_link_token(user) -> str:
    """
    Regénère un token (utile si lien compromis)
    """
    user.telegram_link_token = generate_telegram_link_token()
    db.session.commit()
    return user.telegram_link_token


# =====================================================
# BUILD BOT LINK
# =====================================================

def build_telegram_bot_link(user, bot_username: str) -> str:
    """
    Construit le lien Telegram vers le bot avec token sécurisé
    Exemple :
    https://t.me/MonBot?start=TOKEN
    """
    token = ensure_telegram_link_token(user)
    return f"https://t.me/{bot_username}?start={token}"


# =====================================================
# LINK TELEGRAM ACCOUNT
# =====================================================

def link_telegram_account(user, telegram_user_id: str, telegram_username: str = None):
    """
    Lie le compte Telegram au compte utilisateur
    """
    user.telegram_user_id = str(telegram_user_id)
    user.telegram_username = telegram_username
    user.telegram_verified_at = datetime.utcnow()

    # On invalide le token après utilisation
    user.telegram_link_token = None

    db.session.commit()


# =====================================================
# VALIDATION TOKEN
# =====================================================

def get_user_by_telegram_token(token: str):
    """
    Retrouve un utilisateur via son token Telegram
    """
    if not token:
        return None

    from app.models import User

    return User.query.filter_by(telegram_link_token=token).first()


# =====================================================
# CHECK ACCESS
# =====================================================

def is_telegram_linked(user) -> bool:
    """
    Vérifie si l'utilisateur a lié Telegram
    """
    return bool(user.telegram_user_id)


def has_valid_telegram_access(user) -> bool:
    """
    Vérifie si l'utilisateur peut accéder Telegram
    """
    if not user:
        return False

    if not is_telegram_linked(user):
        return False

    plan = str(getattr(user, "plan", "")).lower()
    return plan in {"basic", "premium", "vip"}


# =====================================================
# DEBUG / LOG
# =====================================================

def log_telegram_link_event(message: str):
    try:
        current_app.logger.info(f"[TELEGRAM LINK] {message}")
    except Exception:
        print(f"[TELEGRAM LINK] {message}")