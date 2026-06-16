# ── ELON RADAR ────────────────────────────────────────────────
@pages_bp.route("/marches/elon-radar")
@pages_bp.route("/<lang_code>/markets/elon-radar")
def elon_radar(lang_code=None):
    normalize_lang(lang_code)
    try:
        from app.services.elon_service import get_elon_radar_cached
        radar = get_elon_radar_cached()
    except Exception as e:
        current_app.logger.error("Elon radar error: %s", e)
        radar = {
            "news": [], "impact_score": 50,
            "sentiment": {"score": 50, "label": "Neutral", "color": "amber"},
            "news_count": 0, "high_events": 0,
            "doge_price": "N/A", "btc_price": "N/A",
            "last_updated": "N/A"
        }

    return render_template(
        "marche/elon_radar.html",
        radar=radar,
        news=radar.get("news", []),
        impact_score=radar.get("impact_score", 50),
        sentiment=radar.get("sentiment", {}),
        doge_price=radar.get("doge_price", "N/A"),
        btc_price=radar.get("btc_price", "N/A"),
        last_updated=radar.get("last_updated", "N/A"),
        current_lang=normalize_lang(lang_code),
    )
