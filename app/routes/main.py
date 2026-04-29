from flask import Blueprint, render_template, jsonify, request, redirect, session, url_for
import os
from app.services.market_service import (
    get_market_updates,
    get_market_overview,
    get_crypto_command_center,
)
from app.services.news_digest_service import prepare_digest_articles
from app.services.telegram_dispatcher import (
    send_morning_briefings,
    send_second_briefings,
    send_daily_news,
    send_breaking_news,
)

main_bp = Blueprint("main", __name__)

SUPPORTED_LANGS = ["fr", "en", "es"]
DEFAULT_LANG = "fr"

CRON_SECRET = os.getenv("CRON_SECRET", "")


def resolve_lang(lang_code=None):
    if lang_code in SUPPORTED_LANGS:
        session["lang"] = lang_code
        return lang_code

    session_lang = session.get("lang")
    if session_lang in SUPPORTED_LANGS:
        return session_lang

    cookie_lang = request.cookies.get("user_lang")
    if cookie_lang in SUPPORTED_LANGS:
        session["lang"] = cookie_lang
        return cookie_lang

    browser_lang = request.accept_languages.best_match(SUPPORTED_LANGS)
    session["lang"] = browser_lang or DEFAULT_LANG

    return session["lang"]


@main_bp.route("/")
def root():
    lang = resolve_lang()
    return redirect(url_for("main.home", lang_code=lang))


@main_bp.route("/<lang_code>/")
def home(lang_code):
    current_lang = resolve_lang(lang_code)

    market_updates = get_market_updates()
    market = get_market_overview()

    return render_template(
        "home.html",
        market_updates=market_updates,
        market=market,
        current_lang=current_lang
    )


@main_bp.route("/<lang_code>/marches/crypto")
def crypto_market(lang_code):
    current_lang = resolve_lang(lang_code)
    market_snapshot = get_crypto_command_center()

    return render_template(
        "crypto.html",
        current_lang=current_lang,
        market_snapshot=market_snapshot
    )


@main_bp.route("/api/crypto/command-center")
def crypto_command_center_api():
    return jsonify({
        "ok": True,
        "data": get_crypto_command_center()
    })


def _cron_authorized() -> bool:
    if not CRON_SECRET:
        return True
    return request.args.get("token", "") == CRON_SECRET


def _unauthorized():
    return jsonify({
        "status": "error",
        "message": "unauthorized"
    }), 403


@main_bp.route("/cron/morning")
def cron_morning():
    if not _cron_authorized():
        return _unauthorized()

    try:
        result = send_morning_briefings()
        return jsonify({"status": "success", "result": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@main_bp.route("/cron/news-morning")
def cron_news_morning():
    if not _cron_authorized():
        return _unauthorized()

    try:
        result = send_daily_news(slot="morning")
        return jsonify({"status": "success", "result": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@main_bp.route("/cron/news-evening")
def cron_news_evening():
    if not _cron_authorized():
        return _unauthorized()

    try:
        result = send_daily_news(slot="evening")
        return jsonify({"status": "success", "result": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@main_bp.route("/cron/midday")
def cron_midday():
    if not _cron_authorized():
        return _unauthorized()

    try:
        content = """
📍 Midday Brief

The market remains in observation around key liquidity zones.
US indices hold a reactive structure while crypto stays sensitive to momentum and macro flow.

Points to monitor:
- intraday levels holding
- reaction of leading assets
- breakout volume confirmation
- trend validation before new exposure
""".strip()

        result = send_second_briefings(
            second_brief_content=content,
            title="Midday Brief",
            slot="midday",
        )

        return jsonify({"status": "success", "result": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@main_bp.route("/cron/evening")
def cron_evening():
    if not _cron_authorized():
        return _unauthorized()

    try:
        content = """
🌙 Evening Brief

The session is closing with focus on risk control and preparation for tomorrow.

Checklist:
- defended zones
- fake breakouts
- leading assets
- profit protection
- next-day scenarios
""".strip()

        result = send_second_briefings(
            second_brief_content=content,
            title="Evening Brief",
            slot="evening",
        )

        return jsonify({"status": "success", "result": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@main_bp.route("/cron/breaking-news")
def cron_breaking_news():
    if not _cron_authorized():
        return _unauthorized()

    try:
        articles = prepare_digest_articles(limit=1, max_age_hours=6)

        if not articles:
            return jsonify({
                "status": "no_news",
                "message": "Aucune breaking news disponible"
            })

        article = articles[0]
        result = send_breaking_news(article)

        return jsonify({
            "status": "success",
            "article_title": article.get("title"),
            "result": result
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500