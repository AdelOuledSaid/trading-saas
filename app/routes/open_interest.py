from flask import Blueprint, render_template, request
from app.services.open_interest_service import OpenInterestService

open_interest_bp = Blueprint(
    "open_interest",
    __name__,
    url_prefix="/marche"
)


def _safe_float(value):
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    txt = str(value).strip().replace("%", "").replace(",", ".")
    txt = txt.replace("+", "").replace("−", "-")
    try:
        return float(txt)
    except ValueError:
        return 0.0


def _clamp(value, min_value=0, max_value=100):
    return max(min_value, min(max_value, value))


def _conviction_score(item):
    c1 = abs(_safe_float(item.get("change_1h_number", item.get("change_1h", 0))))
    c4 = abs(_safe_float(item.get("change_4h_number", item.get("change_4h", 0))))
    c24 = abs(_safe_float(item.get("change_24h_number", item.get("change_24h", 0))))

    score = (c1 * 4.0) + (c4 * 2.5) + (c24 * 1.5)

    bias = (item.get("market_bias") or "").strip().lower()
    if bias in {"bullish", "bearish"}:
        score += 8

    return int(_clamp(round(score), 0, 100))


def _badge_class(market_bias):
    bias = (market_bias or "").strip().lower()
    if bias == "bullish":
        return "bullish"
    if bias == "bearish":
        return "bearish"
    return "neutral"


def _build_dashboard(oi_snapshots, summary):
    total = len(oi_snapshots)

    bullish = sum(1 for x in oi_snapshots if (x.get("market_bias") or "").lower() == "bullish")
    bearish = sum(1 for x in oi_snapshots if (x.get("market_bias") or "").lower() == "bearish")
    neutral = max(0, total - bullish - bearish)

    avg_abs_1h = round(
        sum(abs(_safe_float(x.get("change_1h_number", x.get("change_1h", 0)))) for x in oi_snapshots) / total, 2
    ) if total else 0

    avg_abs_4h = round(
        sum(abs(_safe_float(x.get("change_4h_number", x.get("change_4h", 0)))) for x in oi_snapshots) / total, 2
    ) if total else 0

    avg_abs_24h = round(
        sum(abs(_safe_float(x.get("change_24h_number", x.get("change_24h", 0)))) for x in oi_snapshots) / total, 2
    ) if total else 0

    enriched = []
    high_conviction_count = 0

    for item in oi_snapshots:
        c1 = abs(_safe_float(item.get("change_1h_number", item.get("change_1h", 0))))
        c4 = abs(_safe_float(item.get("change_4h_number", item.get("change_4h", 0))))
        c24 = abs(_safe_float(item.get("change_24h_number", item.get("change_24h", 0))))

        conviction_score = _conviction_score(item)
        anomaly_score = _clamp(int(c1 * 8 + c4 * 5 + c24 * 2))
        squeeze_risk = _clamp(int((c1 * 7) + (c4 * 4) + (conviction_score * 0.35)))

        if conviction_score >= 65:
            high_conviction_count += 1

        enriched_item = dict(item)
        enriched_item["conviction_score"] = conviction_score
        enriched_item["badge_class"] = _badge_class(item.get("market_bias"))
        enriched_item["anomaly_score"] = anomaly_score
        enriched_item["squeeze_risk"] = squeeze_risk
        enriched_item["bar_1h"] = _clamp(int(c1 * 10))
        enriched_item["bar_4h"] = _clamp(int(c4 * 6))
        enriched_item["bar_24h"] = _clamp(int(c24 * 3))
        enriched.append(enriched_item)

    enriched.sort(key=lambda x: (x["conviction_score"], x["squeeze_risk"], x["anomaly_score"]), reverse=True)

    bullish_ratio = int(round((bullish / total) * 100)) if total else 0
    bearish_ratio_percent = int(round((bearish / total) * 100)) if total else 0
    neutral_ratio = int(round((neutral / total) * 100)) if total else 0

    if bullish > bearish:
        directional_pressure = "Bullish tilt"
    elif bearish > bullish:
        directional_pressure = "Bearish tilt"
    else:
        directional_pressure = "Balanced"

    avg_intensity = (avg_abs_1h * 3) + (avg_abs_4h * 2) + avg_abs_24h
    crowding_score = int(_clamp(round(avg_intensity * 2.2 + (high_conviction_count * 4))))
    squeeze_probability = int(_clamp(round((crowding_score * 0.55) + (high_conviction_count * 3))))

    if crowding_score >= 75:
        leverage_pressure = "Extreme"
        volatility_state = "Very high"
        build_up_state = "Aggressive build-up"
        risk_cluster = "Concentrated"
        alert_mode = "High alert"
        regime = {
            "label": "Crowded / squeeze risk",
            "description": "Le marché dérivé est tendu. Le levier est concentré et le risque de mouvement violent augmente."
        }
    elif crowding_score >= 55:
        leverage_pressure = "Elevated"
        volatility_state = "High"
        build_up_state = "Active expansion"
        risk_cluster = "Rising"
        alert_mode = "Elevated watch"
        regime = {
            "label": "Expansion phase",
            "description": "Le marché construit activement des positions. Les actifs leaders peuvent accélérer."
        }
    elif crowding_score >= 35:
        leverage_pressure = "Moderate"
        volatility_state = "Normal"
        build_up_state = "Selective rotation"
        risk_cluster = "Moderate"
        alert_mode = "Normal watch"
        regime = {
            "label": "Structured rotation",
            "description": "Le marché reste sélectif. Certaines poches d’intensité émergent mais sans tension généralisée."
        }
    else:
        leverage_pressure = "Low"
        volatility_state = "Low"
        build_up_state = "Low engagement"
        risk_cluster = "Diffuse"
        alert_mode = "Passive"
        regime = {
            "label": "Neutral / reset",
            "description": "Le levier reste relativement calme. Le marché manque encore de build-up généralisé."
        }

    if bullish > bearish and crowding_score >= 55:
        market_note = "Les flux favorisent une construction haussière avec levier actif. Priorise les actifs top leaderboard."
    elif bearish > bullish and crowding_score >= 55:
        market_note = "La pression vendeuse domine dans un environnement chargé. Le risque de continuation reste élevé."
    elif crowding_score < 35:
        market_note = "Le marché paraît encore peu engagé. Les signaux sont moins puissants tant que le build-up reste faible."
    else:
        market_note = "Le marché reste mixte. Il faut privilégier les actifs qui concentrent conviction, anomalies et squeeze risk."

    alerts = []
    for item in enriched[:6]:
        score = item["conviction_score"]
        squeeze = item["squeeze_risk"]
        anomaly = item["anomaly_score"]

        if score >= 80 or squeeze >= 80:
            level = "Critical"
            level_class = "high"
        elif score >= 60 or squeeze >= 60 or anomaly >= 60:
            level = "Elevated"
            level_class = "medium"
        else:
            level = "Monitor"
            level_class = "low"

        if item.get("market_bias") == "Bullish":
            message = f"Build-up haussier sur {item.get('asset')}. Surveille une continuation si le prix confirme."
        elif item.get("market_bias") == "Bearish":
            message = f"Pression vendeuse structurée sur {item.get('asset')}. Risque de faiblesse prolongée."
        else:
            message = f"Lecture mixte sur {item.get('asset')}. Attendre confirmation directionnelle avant d’agir."

        alerts.append({
            "asset": item.get("asset"),
            "level": level,
            "level_class": level_class,
            "message": message,
            "conviction_score": score,
            "squeeze_risk": squeeze,
            "anomaly_score": anomaly,
        })

    return {
        "bullish_count": bullish,
        "bearish_count": bearish,
        "neutral_count": neutral,
        "bullish_ratio": bullish_ratio,
        "bearish_ratio_percent": bearish_ratio_percent,
        "neutral_ratio": neutral_ratio,
        "directional_pressure": directional_pressure,
        "high_conviction_count": high_conviction_count,
        "avg_abs_1h": avg_abs_1h,
        "avg_abs_4h": avg_abs_4h,
        "avg_abs_24h": avg_abs_24h,
        "crowding_score": crowding_score,
        "squeeze_probability": squeeze_probability,
        "leverage_pressure": leverage_pressure,
        "volatility_state": volatility_state,
        "build_up_state": build_up_state,
        "risk_cluster": risk_cluster,
        "alert_mode": alert_mode,
        "regime": regime,
        "market_note": market_note,
        "priority_assets": enriched[:6],
        "anomalies": sorted(enriched, key=lambda x: x["anomaly_score"], reverse=True)[:5],
        "alerts": alerts,
    }


@open_interest_bp.route("/open-interest")
def open_interest_page():
    service = OpenInterestService()

    asset = (request.args.get("asset", "") or "").strip().upper()
    conviction = (request.args.get("conviction", "") or "").strip().lower()

    try:
        limit = int(request.args.get("limit", 12))
    except (TypeError, ValueError):
        limit = 12

    if limit < 1:
        limit = 1
    if limit > 50:
        limit = 50

    valid_assets = {"BTC", "ETH", "SOL", "XRP", "BNB"}

    asset_filter = asset if asset in valid_assets else None
    only_high_conviction = conviction == "high"

    oi_snapshots = service.get_snapshots_dict(
        asset=asset_filter,
        only_high_conviction=only_high_conviction,
        limit=limit,
    )

    for item in oi_snapshots:
        item["conviction_score"] = _conviction_score(item)

    summary = service.get_summary()
    top_snapshots = service.get_top_snapshots(limit=5)

    active_filters = {
        "asset": asset_filter or "",
        "conviction": "high" if only_high_conviction else "",
        "limit": limit,
    }

    dashboard = _build_dashboard(oi_snapshots, summary)

    return render_template(
        "marche/open_interest.html",
        oi_snapshots=oi_snapshots,
        summary=summary,
        top_snapshots=top_snapshots,
        active_filters=active_filters,
        dashboard=dashboard,
    )