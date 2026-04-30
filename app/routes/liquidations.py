from flask import Blueprint, render_template, request, jsonify
from app.services.liquidations_service import get_liquidations_service

liquidations_bp = Blueprint(
    "liquidations",
    __name__,
    url_prefix="/marche"
)


def _to_number(value):
    if value is None:
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().upper()
    text = text.replace("$", "").replace(",", "").replace(" ", "")

    multiplier = 1.0

    if text.endswith("M"):
        multiplier = 1_000_000
        text = text[:-1]
    elif text.endswith("K"):
        multiplier = 1_000
        text = text[:-1]
    elif text.endswith("B"):
        multiplier = 1_000_000_000
        text = text[:-1]

    try:
        return float(text) * multiplier
    except (TypeError, ValueError):
        return 0.0


def _safe_summary(summary):
    if not isinstance(summary, dict):
        summary = {}

    long_count = summary.get("long_count", 0) or 0
    short_count = summary.get("short_count", 0) or 0

    long_value_raw = summary.get("long_value", 0)
    short_value_raw = summary.get("short_value", 0)

    long_value_numeric = summary.get("long_value_numeric")
    short_value_numeric = summary.get("short_value_numeric")

    if long_value_numeric is None:
        long_value_numeric = _to_number(long_value_raw)

    if short_value_numeric is None:
        short_value_numeric = _to_number(short_value_raw)

    dominant_bias = summary.get("dominant_bias")

    if not dominant_bias:
        if short_value_numeric > long_value_numeric:
            dominant_bias = "Bullish"
        elif long_value_numeric > short_value_numeric:
            dominant_bias = "Bearish"
        else:
            dominant_bias = "Neutral"

    summary["total_events"] = summary.get("total_events", 0) or 0
    summary["total_value"] = summary.get("total_value", "$0.0M") or "$0.0M"
    summary["long_value"] = summary.get("long_value", "$0.0M") or "$0.0M"
    summary["short_value"] = summary.get("short_value", "$0.0M") or "$0.0M"
    summary["long_count"] = long_count
    summary["short_count"] = short_count
    summary["high_impact_count"] = summary.get("high_impact_count", 0) or 0
    summary["dominant_bias"] = dominant_bias
    summary["long_value_numeric"] = long_value_numeric
    summary["short_value_numeric"] = short_value_numeric
    summary["pressure_ratio"] = summary.get("pressure_ratio", 50) or 50
    summary["market_state"] = summary.get("market_state", "Waiting live feed") or "Waiting live feed"
    summary["imbalance_strength"] = summary.get("imbalance_strength", "Weak") or "Weak"

    return summary


def _get_filters():
    asset = (request.args.get("asset", "") or "").strip().upper()
    side = (request.args.get("side", "") or "").strip().lower()
    impact = (request.args.get("impact", "") or "").strip().lower()

    try:
        limit = int(request.args.get("limit", 12))
    except (TypeError, ValueError):
        limit = 12

    if limit < 1:
        limit = 1
    if limit > 50:
        limit = 50

    valid_assets = {"BTC", "ETH", "SOL", "XRP", "BNB"}
    valid_sides = {"long", "short"}

    asset_filter = asset if asset in valid_assets else None
    side_filter = side if side in valid_sides else None
    only_high_impact = impact == "high"

    active_filters = {
        "asset": asset_filter or "",
        "side": side_filter or "",
        "impact": "high" if only_high_impact else "",
        "limit": limit,
    }

    return asset_filter, side_filter, only_high_impact, limit, active_filters


@liquidations_bp.route("/liquidations")
@liquidations_bp.route("/<lang_code>/liquidations")
def liquidations_page(lang_code=None):
    service = get_liquidations_service()

    asset_filter, side_filter, only_high_impact, limit, active_filters = _get_filters()

    liquidation_events = service.get_events_dict(
        asset=asset_filter,
        side=side_filter,
        only_high_impact=only_high_impact,
        limit=limit,
    )

    summary = _safe_summary(service.get_summary())
    top_events = service.get_top_events(limit=5)

    return render_template(
        "marche/liquidations.html",
        liquidation_events=liquidation_events,
        summary=summary,
        top_events=top_events,
        active_filters=active_filters,
    )


@liquidations_bp.route("/api/liquidations/live")
def liquidations_live_api():
    service = get_liquidations_service()

    asset_filter, side_filter, only_high_impact, limit, _active_filters = _get_filters()

    liquidation_events = service.get_events_dict(
        asset=asset_filter,
        side=side_filter,
        only_high_impact=only_high_impact,
        limit=limit,
    )

    top_events = service.get_top_events(limit=5)
    summary = _safe_summary(service.get_summary())

    return jsonify({
        "ok": True,
        "summary": summary,
        "events": liquidation_events,
        "top_events": top_events,
        "service_running": service.is_running(),
    })