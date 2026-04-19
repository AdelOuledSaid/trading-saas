from datetime import datetime
from flask import current_app

from app.extensions import db
from app.models import DailyBriefing
from app.services.market_service import get_btc_data, get_gold_data, get_economic_calendar
from ai_briefing import generate_daily_briefing


# =========================
# HELPERS
# =========================
def _clean_text(text: str) -> str:
    return (text or "").strip()


def _truncate_safely(text: str, max_len: int) -> str:
    text = _clean_text(text)
    if len(text) <= max_len:
        return text

    truncated = text[:max_len].rstrip()

    last_break = max(
        truncated.rfind("\n"),
        truncated.rfind(". "),
        truncated.rfind(" "),
    )

    if last_break > int(max_len * 0.6):
        truncated = truncated[:last_break].rstrip()

    return truncated.rstrip() + "..."


# =========================
# PLAN VERSIONS
# =========================
def build_basic_briefing(content: str) -> str:
    base = _truncate_safely(content, 850)

    return (
        f"{base}\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📌 <b>Basic Focus</b>\n"
        "- lecture simple du marché\n"
        "- zones principales à surveiller\n"
        "- prudence avant toute entrée\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🔒 <b>Résumé incomplet volontairement</b>\n"
        "La version détaillée avec davantage de contexte reste réservée aux membres supérieurs.\n\n"
        "💎 <b>Upgrade pour accéder à :</b>\n"
        "• analyse plus complète\n"
        "• meilleures zones de réaction\n"
        "• opportunités du jour\n"
    ).strip()


def build_premium_briefing(content: str) -> str:
    base = _clean_text(content)

    return (
        f"{base}\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📊 <b>Premium Focus</b>\n"
        "- lecture détaillée de la tendance\n"
        "- actifs prioritaires\n"
        "- zones de réaction importantes\n"
        "- prudence sur les faux breakouts\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🔒 <b>VIP Edge</b>\n"
        "Les setups sniper, le timing d’exécution et la lecture desk avancée restent réservés VIP.\n"
    ).strip()


def build_vip_briefing(content: str) -> str:
    base = _clean_text(content)

    return (
        f"{base}\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🔒 <b>VIP Focus</b>\n"
        "- zones de liquidité prioritaires\n"
        "- actifs à surveiller en priorité\n"
        "- lecture macro / momentum\n"
        "- scénarios continuation / invalidation\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💎 <b>Desk Insight</b>\n"
        "- surveiller les sweeps de liquidité\n"
        "- éviter les entrées impulsives\n"
        "- privilégier les setups propres avec bon RR\n"
        "- attendre confirmation avant exécution agressive\n"
    ).strip()


def get_briefing_content_for_plan(raw_content: str, plan: str) -> str:
    normalized = (plan or "basic").strip().lower()

    if normalized == "vip":
        return build_vip_briefing(raw_content)

    if normalized == "premium":
        return build_premium_briefing(raw_content)

    return build_basic_briefing(raw_content)


# =========================
# DATABASE / DAILY BRIEFING
# =========================
def ensure_daily_briefing():
    today = datetime.utcnow().date()
    existing = DailyBriefing.query.filter_by(date=today).first()

    if existing:
        return existing

    try:
        btc_data = get_btc_data()
        gold_data = get_gold_data()
        eco_data = get_economic_calendar()

        current_app.logger.info("BRIEFING DATA | BTC=%s", btc_data)
        current_app.logger.info("BRIEFING DATA | GOLD=%s", gold_data)
        current_app.logger.info("BRIEFING DATA | ECO=%s", eco_data)

        raw_content = generate_daily_briefing(btc_data, gold_data, eco_data)
        raw_content = _clean_text(raw_content)

        if not raw_content:
            current_app.logger.warning("Briefing généré vide.")
            return None

        briefing = DailyBriefing(
            date=today,
            content=raw_content,
        )

        db.session.add(briefing)
        db.session.commit()

        current_app.logger.info("Briefing du jour généré avec succès.")
        return briefing

    except Exception as e:
        current_app.logger.error("Erreur génération briefing: %s", repr(e))
        return None


# =========================
# READY-TO-USE HELPERS
# =========================
def get_daily_briefing_for_plan(plan: str):
    briefing = ensure_daily_briefing()
    if not briefing or not getattr(briefing, "content", None):
        return None

    content = get_briefing_content_for_plan(briefing.content, plan)

    return type(
        "PlanBriefing",
        (),
        {
            "date": briefing.date,
            "created_at": briefing.created_at,
            "content": content,
        },
    )()


def get_basic_daily_briefing():
    return get_daily_briefing_for_plan("basic")


def get_premium_daily_briefing():
    return get_daily_briefing_for_plan("premium")


def get_vip_daily_briefing():
    return get_daily_briefing_for_plan("vip")