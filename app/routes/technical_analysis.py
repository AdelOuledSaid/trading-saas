from flask import Blueprint, render_template, request, jsonify
from flask_login import current_user

from app.services.technical_analysis_service import TechnicalAnalysisService
from app.services.ai_summary_service import AISummaryService

technical_analysis_bp = Blueprint("technical_analysis", __name__)


# =========================
# PAGE
# =========================
@technical_analysis_bp.route("/technical-analysis")
@technical_analysis_bp.route("/<lang_code>/technical-analysis")
def technical_analysis_page(lang_code=None):
    return render_template("technical_analysis.html")


# =========================
# MAIN ANALYSIS
# =========================
@technical_analysis_bp.route("/api/technical-analysis")
def technical_analysis_api():
    token = request.args.get("token", "BTC")
    interval = request.args.get("interval", "1h")
    indicator = request.args.get("indicator", "stochasticrsi")

    ta = TechnicalAnalysisService()
    ai = AISummaryService()

    analysis = ta.analyze(
        token=token,
        interval=interval,
        indicator=indicator,
        include_multi_tf=True,
    )
    data = analysis.to_dict()

    try:
        data["ai_summary"] = ai.summarize(data["summary_context"])
    except Exception:
        data["ai_summary"] = (
            f"{data.get('token', 'Asset')} {data.get('interval', '').upper()} "
            f"bias {data.get('bias', 'mixed')} with confidence {data.get('confidence', '--')}%."
        )

    return jsonify(data)


# =========================
# PREMIUM API
# =========================
@technical_analysis_bp.route("/api/technical-analysis/premium")
def premium_insight():
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


# =========================
# VIP API
# =========================
@technical_analysis_bp.route("/api/technical-analysis/vip")
def vip_insight():
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
        return jsonify(payload)
    except Exception as exc:
        return jsonify({
            "type": insight_type,
            "vip_data": None,
            "error": str(exc),
        }), 500


# =========================
# TOKENS
# =========================
@technical_analysis_bp.route("/api/technical-analysis/tokens")
def tokens():
    ta = TechnicalAnalysisService()
    return jsonify({"tokens": ta.get_available_tokens()})