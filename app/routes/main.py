from flask import Blueprint, render_template, jsonify, request
import os

from app.services.market_service import get_market_updates
from app.services.telegram_dispatcher import (
    send_morning_briefings,
    send_second_briefings,
    send_daily_news,
)

main_bp = Blueprint("main", __name__)

CRON_SECRET = os.getenv("CRON_SECRET", "")


def _cron_authorized() -> bool:
    if not CRON_SECRET:
        return True
    return request.args.get("token", "") == CRON_SECRET


def _unauthorized():
    return jsonify({
        "status": "error",
        "message": "unauthorized"
    }), 403


@main_bp.route("/")
def home():
    market_updates = get_market_updates()
    return render_template("home.html", market_updates=market_updates)


@main_bp.route("/cron/morning")
def cron_morning():
    if not _cron_authorized():
        return _unauthorized()

    try:
        result = send_morning_briefings()
        return jsonify({
            "status": "success",
            "result": result
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@main_bp.route("/cron/news-morning")
def cron_news_morning():
    if not _cron_authorized():
        return _unauthorized()

    try:
        result = send_daily_news(slot="morning")
        return jsonify({
            "status": "success",
            "result": result
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@main_bp.route("/cron/news-evening")
def cron_news_evening():
    if not _cron_authorized():
        return _unauthorized()

    try:
        result = send_daily_news(slot="evening")
        return jsonify({
            "status": "success",
            "result": result
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@main_bp.route("/cron/midday")
def cron_midday():
    if not _cron_authorized():
        return _unauthorized()

    try:
        content = """
📍 Midday Brief

Le marché reste en observation sur les zones clés.
Privilégier la patience et attendre une confirmation nette.

Checklist :
- niveaux intraday
- volume sur cassure
- réaction des actifs leaders
- prudence avant exposition
""".strip()

        result = send_second_briefings(
            second_brief_content=content,
            title="Midday Brief",
            slot="midday",
        )

        return jsonify({
            "status": "success",
            "result": result
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@main_bp.route("/cron/evening")
def cron_evening():
    if not _cron_authorized():
        return _unauthorized()

    try:
        content = """
🌙 Evening Brief

La session se termine. On prépare les scénarios du lendemain
et on évite le surtrading.

Checklist :
- zones défendues
- faux breakouts
- actifs leaders
- protection des gains
""".strip()

        result = send_second_briefings(
            second_brief_content=content,
            title="Evening Brief",
            slot="evening",
        )

        return jsonify({
            "status": "success",
            "result": result
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500