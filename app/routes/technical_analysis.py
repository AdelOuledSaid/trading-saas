from flask import Blueprint, render_template, request, jsonify
from flask_login import current_user

from app.services.technical_analysis_service import TechnicalAnalysisService
from app.services.ai_summary_service import AISummaryService

technical_analysis_bp = Blueprint("technical_analysis", __name__)


PREMIUM_LOCKED_REPLAY = {
    "count": None,
    "winrate": None,
    "avg_confidence": None,
    "last_setups": [],
    "best_bias": None,
    "locked": True,
}

VIP_LOCKED_PAYLOAD = {
    "score": None,
    "execution_mode": None,
    "risk_profile": None,
    "bullish_scenario": None,
    "bearish_scenario": None,
    "neutral_scenario": None,
    "desk_notes": None,
    "telegram_alert_candidate": False,
    "telegram_linked": False,
    "locked": True,
}


def _is_authenticated() -> bool:
    try:
        return bool(getattr(current_user, "is_authenticated", False))
    except Exception:
        return False


def _current_plan() -> str:
    if not _is_authenticated():
        return "free"
    return str(getattr(current_user, "plan", "free") or "free").strip().lower()


def _telegram_linked() -> bool:
    if not _is_authenticated():
        return False

    candidates = [
        getattr(current_user, "telegram_linked", None),
        getattr(current_user, "has_telegram", None),
        getattr(current_user, "telegram_chat_id", None),
        getattr(current_user, "telegram_id", None),
        getattr(current_user, "telegram_user_id", None),
        getattr(current_user, "telegram_username", None),
    ]
    return any(bool(value) for value in candidates)


def _access_payload() -> dict:
    plan = _current_plan()
    return {
        "plan": plan,
        "is_premium": plan in {"premium", "vip"},
        "is_vip": plan == "vip",
        "telegram_linked": _telegram_linked(),
    }


def _apply_access_control(data: dict) -> dict:
    access = _access_payload()
    data["access"] = access

    if not access["is_premium"]:
        data["premium"] = None
        data["setup_replay"] = dict(PREMIUM_LOCKED_REPLAY)
        data["vip"] = dict(VIP_LOCKED_PAYLOAD)
        return data

    vip_payload = data.get("vip") or {}
    vip_payload["telegram_linked"] = access["telegram_linked"]
    if not access["is_vip"]:
        vip_payload["telegram_alert_candidate"] = False
    data["vip"] = vip_payload
    return data


def _fallback_ai_advanced_analysis(data: dict) -> dict:
    levels = data.get("levels", {})
    orderflow = data.get("orderflow", {})
    indicators = data.get("indicators", {})
    mtf = data.get("multi_timeframe", {}) or {}
    confluence = mtf.get("confluence", {}) or {}

    return {
        "market_structure": data.get("summary_context", {}).get("market_structure", "unknown_structure"),
        "momentum": data.get("summary_context", {}).get("momentum_regime", "neutral_momentum"),
        "simulated_orderflow": {
            "state": orderflow.get("state"),
            "dominant_signal": orderflow.get("dominant_signal"),
            "buyer_aggression": orderflow.get("buyer_aggression"),
            "seller_aggression": orderflow.get("seller_aggression"),
            "absorption": orderflow.get("absorption"),
            "exhaustion": orderflow.get("exhaustion"),
            "delta_pressure": orderflow.get("delta_pressure"),
            "imbalance_zone": orderflow.get("imbalance_zone"),
            "close_position": orderflow.get("close_position"),
            "body_ratio": orderflow.get("body_ratio"),
            "volume_acceleration": orderflow.get("volume_acceleration"),
        },
        "multi_timeframe_context": {
            "15m": (mtf.get("timeframes") or {}).get("15m"),
            "1h": (mtf.get("timeframes") or {}).get("1h"),
            "4h": (mtf.get("timeframes") or {}).get("4h"),
            "1d": (mtf.get("timeframes") or {}).get("1d"),
            "confluence_score": confluence.get("score"),
            "alignment": confluence.get("alignment"),
            "dominant_bias": confluence.get("dominant_bias"),
            "entry_quality": confluence.get("entry_quality"),
        },
        "bull_scenario": {
            "title": "bull continuation",
            "trigger": f"Hold above pivot {levels.get('pivot')} and sustain buyer support.",
            "confirmation": f"Break above {levels.get('resistance_1')} with rising volume.",
            "targets": [levels.get("resistance_1"), levels.get("resistance_2")],
        },
        "bear_scenario": {
            "title": "bear continuation",
            "trigger": f"Lose pivot {levels.get('pivot')} and fail reclaim.",
            "confirmation": f"Acceptance below {levels.get('support_1')} with seller control.",
            "targets": [levels.get("support_1"), levels.get("support_2")],
        },
        "neutral_scenario": {
            "title": "range / wait",
            "trigger": f"Price remains between {levels.get('support_1')} and {levels.get('resistance_1')}.",
            "confirmation": "Wait for breakout confirmed by body expansion and volume.",
            "targets": [levels.get("pivot")],
        },
        "invalidation": (
            f"Current thesis invalidates if price loses or reclaims pivot {levels.get('pivot')} against the active bias."
        ),
        "execution_note": (
            f"Trend={indicators.get('trend')} | RSI={indicators.get('rsi')} | MFI={indicators.get('mfi')} | "
            f"orderflow={orderflow.get('dominant_signal', orderflow.get('state'))} | confluence={confluence.get('score')}"
        ),
    }


@technical_analysis_bp.route("/technical-analysis")
@technical_analysis_bp.route("/<lang_code>/technical-analysis")
def technical_analysis_page(lang_code=None):
    return render_template("technical_analysis.html")


@technical_analysis_bp.route("/api/technical-analysis")
def technical_analysis_api():
    token = request.args.get("token", "BTC")
    interval = request.args.get("interval", "1h")
    indicator = request.args.get("indicator", "stochasticrsi")

    ta = TechnicalAnalysisService()

    try:
        analysis = ta.analyze(
            token=token,
            interval=interval,
            indicator=indicator,
            include_multi_tf=False,  # ULTRA FAST: avoids 4 extra Binance calls on page load
        )
        data = analysis.to_dict()
    except Exception as exc:
        # Never leave the frontend with an empty/white page.
        return jsonify({
            "error": True,
            "message": "Technical analysis temporarily unavailable. Please retry in a few seconds.",
            "details": str(exc),
            "token": token.upper(),
            "interval": interval,
            "indicator": indicator,
            "access": _access_payload(),
        }), 200

    # ULTRA FAST: no slow AI call on initial page load.
    data["ai_summary"] = (
        f"{data.get('token', 'Asset')} {str(data.get('interval', '')).upper()} "
        f"bias {data.get('bias', 'mixed')} with confidence {data.get('confidence', '--')}%."
    )

    if not data.get("ai_advanced_analysis"):
        data["ai_advanced_analysis"] = _fallback_ai_advanced_analysis(data)

    data = _apply_access_control(data)
    return jsonify(data)

@technical_analysis_bp.route("/api/technical-analysis/premium")
def premium_insight():
    access = _access_payload()
    if not access["is_premium"]:
        return jsonify({
            "type": request.args.get("type", "premium-overview"),
            "premium_data": None,
            "locked": True,
            "required_plan": "premium",
        }), 403

    token = request.args.get("token", "BTC")
    interval = request.args.get("interval", "1h")
    indicator = request.args.get("indicator", "stochasticrsi")
    insight_type = request.args.get("type", "premium-overview")

    ta = TechnicalAnalysisService()

    try:
        payload = ta.build_premium_insight(
            token=token,
            interval=interval,
            indicator=indicator,
            insight_type=insight_type,
        )
        return jsonify(payload)
    except Exception as exc:
        return jsonify({
            "type": insight_type,
            "premium_data": None,
            "error": str(exc),
        }), 500


@technical_analysis_bp.route("/api/technical-analysis/vip")
def vip_insight():
    access = _access_payload()
    if not access["is_premium"]:
        return jsonify({
            "type": request.args.get("type", "vip-overview"),
            "vip_data": None,
            "locked": True,
            "required_plan": "premium",
        }), 403

    token = request.args.get("token", "BTC")
    interval = request.args.get("interval", "1h")
    indicator = request.args.get("indicator", "stochasticrsi")
    insight_type = request.args.get("type", "vip-overview")

    ta = TechnicalAnalysisService()

    try:
        payload = ta.build_vip_insight(
            token=token,
            interval=interval,
            indicator=indicator,
            insight_type=insight_type,
        )
        if isinstance(payload, dict):
            payload["telegram_linked"] = access["telegram_linked"]
            if not access["is_vip"]:
                payload["telegram_alert_candidate"] = False
        return jsonify(payload)
    except Exception as exc:
        return jsonify({
            "type": insight_type,
            "vip_data": None,
            "error": str(exc),
        }), 500


@technical_analysis_bp.route("/api/technical-analysis/tokens")
def tokens():
    ta = TechnicalAnalysisService()
    return jsonify({"tokens": ta.get_available_tokens()})
