from flask import Blueprint, render_template, request
from flask_login import current_user
from app.services.market_data_service import MarketDataService
from app.services.free_unlocks_service import FreeUnlocksService

token_unlocks_bp = Blueprint("token_unlocks", __name__, url_prefix="/marches")


@token_unlocks_bp.app_context_processor
def inject_unlock_alert():
    try:
        service = FreeUnlocksService()
        summary = service.get_alert_summary(days=7)

        return {
            "unlock_menu_alert": summary.get("has_alert", False),
            "unlock_menu_level": summary.get("level", "low"),
        }
    except Exception:
        return {
            "unlock_menu_alert": False,
            "unlock_menu_level": "low",
        }


def user_has_unlocks_premium():
    try:
        if not current_user.is_authenticated:
            return False
        plan = str(getattr(current_user, "plan", "free") or "free").lower()
        return plan in ["premium", "vip"]
    except Exception:
        return False


def build_unlock_insights(top_unlocks):
    if not top_unlocks:
        return {
            "bias_title": "Neutral Unlock Pressure",
            "bias_text": "Aucun unlock majeur détecté sur la période en cours.",
            "signal_title": "Monitoring Mode",
            "signal_text": "Le marché ne montre pas de concentration inhabituelle de risque unlock.",
            "focus_title": "Low Activity Window",
            "focus_text": "Fenêtre calme avec pression d’offre limitée.",
            "setup_type": "Low Event Density",
            "expected_behavior": "Volatilité modérée",
            "action_type": "Watchlist only",
        }

    high_count = sum(1 for x in top_unlocks if x.get("risk_level") == "high")
    medium_count = sum(1 for x in top_unlocks if x.get("risk_level") == "medium")
    sell_count = sum(1 for x in top_unlocks if x.get("signal_level") == "sell")
    caution_count = sum(1 for x in top_unlocks if x.get("signal_level") == "caution")

    biggest = max(top_unlocks, key=lambda x: x.get("value", 0))
    nearest = min(top_unlocks, key=lambda x: x.get("days_until", 999))

    total_value = sum(x.get("value", 0) for x in top_unlocks[:5])

    if high_count >= 2 or biggest.get("market_cap_ratio", 0) >= 5:
        bias_title = "Unlock Pressure Elevated"
        bias_text = (
            f"Plusieurs unlocks à risque élevé sont détectés. "
            f"Le plus lourd reste {biggest['token']} avec {biggest['market_cap_ratio']:.2f}% de market cap."
        )
    elif medium_count >= 2:
        bias_title = "Moderate Unlock Pressure"
        bias_text = (
            f"Le marché présente une pression d’offre modérée avec plusieurs tokens en zone sensible. "
            f"Surveillance renforcée recommandée."
        )
    else:
        bias_title = "Contained Unlock Risk"
        bias_text = (
            f"Les unlocks suivis restent contenus. L’impact potentiel semble concentré sur quelques actifs seulement."
        )

    if sell_count >= 1:
        signal_title = "Sell Bias Dominant"
        signal_text = (
            f"Le moteur détecte au moins un setup de réduction de risque. "
            f"{nearest['token']} reste le token le plus proche avec un unlock à J-{nearest['days_until']}."
        )
    elif caution_count >= 1:
        signal_title = "Caution Bias Dominant"
        signal_text = (
            f"La volatilité peut monter avant certains unlocks. "
            f"Attendre confirmation avant exposition agressive."
        )
    else:
        signal_title = "Watch Bias Dominant"
        signal_text = (
            f"Pas de signal vendeur extrême détecté, mais les tokens proches doivent rester sous surveillance."
        )

    focus_title = "Focus 7 Days"
    focus_text = (
        f"Les principaux unlocks proches représentent environ ${total_value:,.0f}. "
        f"Le prochain événement clé concerne {nearest['token']} à J-{nearest['days_until']}."
    )

    if sell_count >= 1:
        setup_type = "Pre-Unlock Defensive"
        expected_behavior = "Volatilité élevée"
        action_type = "Reduce risk"
    elif caution_count >= 1:
        setup_type = "Pre-Unlock Caution"
        expected_behavior = "Volatilité modérée"
        action_type = "Wait / Confirm"
    else:
        setup_type = "Monitoring Window"
        expected_behavior = "Flux sélectif"
        action_type = "Watch only"

    return {
        "bias_title": bias_title,
        "bias_text": bias_text,
        "signal_title": signal_title,
        "signal_text": signal_text,
        "focus_title": focus_title,
        "focus_text": focus_text,
        "setup_type": setup_type,
        "expected_behavior": expected_behavior,
        "action_type": action_type,
    }


@token_unlocks_bp.route("/token-unlocks")
def token_unlocks_page():
    market_service = MarketDataService()
    unlocks_service = FreeUnlocksService()

    snapshot = market_service.get_global_market_snapshot()
    watchlist = market_service.get_watchlist()

    unlock_chart = unlocks_service.get_chart(days=30)
    top_unlocks = unlocks_service.get_top_unlocks(days=30, limit=10)
    alert_summary = unlocks_service.get_alert_summary(days=7)

    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    calendar_data = unlocks_service.get_calendar_month(year=year, month=month)

    max_unlock_value = max((item["value"] for item in unlock_chart), default=1)
    unlock_insights = build_unlock_insights(top_unlocks)

    return render_template(
        "marche/token_unlocks.html",
        snapshot=snapshot,
        watchlist=watchlist,
        unlock_chart=unlock_chart,
        top_unlocks=top_unlocks,
        max_unlock_value=max_unlock_value,
        alert_summary=alert_summary,
        calendar_data=calendar_data,
        is_unlocks_premium=user_has_unlocks_premium(),
        unlock_insights=unlock_insights,
    )