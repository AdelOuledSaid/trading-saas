from flask import Blueprint, render_template, jsonify
from app.services.market_service import get_market_updates
from app.services.telegram_dispatcher import send_morning_briefings

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def home():
    market_updates = get_market_updates()
    return render_template("home.html", market_updates=market_updates)


# 🔥 ROUTE CRON (briefing automatique)
@main_bp.route("/cron/morning")
def cron_morning():
    try:
        result = send_morning_briefings()
        return jsonify({
            "status": "success",
            "result": str(result)
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500