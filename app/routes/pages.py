from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from flask_login import current_user, login_required

from app.models import Signal
from app.services.whale_tracking_service import WhaleTrackingService
from app.services.market_service import get_crypto_command_center
from flask import jsonify
from app.services.technical_analysis_service import TechnicalAnalysisService
from app.services.ai_summary_service import AISummaryService
pages_bp = Blueprint("pages", __name__)

SUPPORTED_LANGS = ["fr", "en", "es"]
DEFAULT_LANG = "fr"


# =========================================================
# HELPERS
# =========================================================
def normalize_lang(lang_code=None):
    """
    Retourne une langue valide.
    Priorité:
    1) lang_code depuis l'URL
    2) session
    3) défaut
    """
    if lang_code in SUPPORTED_LANGS:
        session["lang"] = lang_code
        return lang_code

    session_lang = session.get("lang")
    if session_lang in SUPPORTED_LANGS:
        return session_lang

    return DEFAULT_LANG


def lang_url(endpoint, lang_code=None, **kwargs):
    """
    Helper pour générer les URLs en gardant la langue courante.
    """
    current_lang = normalize_lang(lang_code)
    return url_for(endpoint, lang_code=current_lang, **kwargs)


def user_has_academy_access():
    try:
        if not current_user.is_authenticated:
            return False

        user_plan = str(getattr(current_user, "plan", "free") or "free").lower()
        return user_plan in ["premium", "vip"]
    except Exception:
        return False


def get_user_plan():
    try:
        if not current_user.is_authenticated:
            return "free"
        return str(getattr(current_user, "plan", "free") or "free").lower()
    except Exception:
        return "free"


def academy_progress():
    return session.get(
        "academy_progress",
        {
            "level1": 35,
            "level2": 0,
            "level3": 0,
            "certificate_ready": False,
        },
    )


# =========================================================
# LEGAL / STATIC PAGES
# Compatible old URLs + SEO multilingual URLs
# =========================================================
@pages_bp.route("/mentions-legales")
@pages_bp.route("/<lang_code>/mentions-legales")
def mentions_legales(lang_code=None):
    normalize_lang(lang_code)
    return render_template("mentions_legales.html")


@pages_bp.route("/privacy")
@pages_bp.route("/<lang_code>/privacy")
def privacy(lang_code=None):
    normalize_lang(lang_code)
    return render_template("privacy.html")


@pages_bp.route("/cgu")
@pages_bp.route("/<lang_code>/cgu")
def cgu(lang_code=None):
    normalize_lang(lang_code)
    return render_template("cgu.html")


@pages_bp.route("/faq")
@pages_bp.route("/<lang_code>/faq")
def faq_page(lang_code=None):
    normalize_lang(lang_code)
    return render_template("faq.html")


@pages_bp.route("/contact")
@pages_bp.route("/<lang_code>/contact")
def contact(lang_code=None):
    normalize_lang(lang_code)
    return render_template("contact.html")


@pages_bp.route("/search")
@pages_bp.route("/<lang_code>/search")
def search_page(lang_code=None):
    normalize_lang(lang_code)
    query = request.args.get("q", "")
    return render_template("search.html", query=query)


@pages_bp.route("/about")
@pages_bp.route("/<lang_code>/about")
def about(lang_code=None):
    normalize_lang(lang_code)
    return render_template("about.html")


# =========================================================
# TRADING LAB
# =========================================================
@pages_bp.route("/trading-lab")
@pages_bp.route("/<lang_code>/trading-lab")
def trading_lab(lang_code=None):
    normalize_lang(lang_code)
    return render_template(
        "trading_lab/index.html",
        academy_progress={"level1": 0, "level2": 0, "level3": 0, "pro": 0}
    )


@pages_bp.route("/trading-lab/structure")
@pages_bp.route("/<lang_code>/trading-lab/structure")
def lab_structure(lang_code=None):
    normalize_lang(lang_code)
    return render_template("trading_lab/structure.html")


@pages_bp.route("/trading-lab/risk")
@pages_bp.route("/<lang_code>/trading-lab/risk")
def lab_risk(lang_code=None):
    normalize_lang(lang_code)
    return render_template("trading_lab/risk.html")


@pages_bp.route("/trading-lab/psychology")
@pages_bp.route("/<lang_code>/trading-lab/psychology")
def lab_psychology(lang_code=None):
    normalize_lang(lang_code)
    return render_template("trading_lab/psychology.html")


# =========================================================
# MARKETS
# On garde les anciennes URLs FR + nouvelles URLs SEO
# =========================================================
@pages_bp.route("/marches/crypto")
@pages_bp.route("/<lang_code>/markets/crypto")
def market_crypto(lang_code=None):
    normalize_lang(lang_code)

    try:
        market_snapshot = get_crypto_command_center()
    except Exception:
        market_snapshot = None

    return render_template(
        "marche/crypto.html",
        market_snapshot=market_snapshot
    )


@pages_bp.route("/marches/forex")
@pages_bp.route("/<lang_code>/markets/forex")
def market_forex(lang_code=None):
    normalize_lang(lang_code)
    return render_template("marche/forex.html")


@pages_bp.route("/marches/opportunites")
@pages_bp.route("/<lang_code>/markets/opportunities")
def market_opportunities(lang_code=None):
    normalize_lang(lang_code)
    return render_template("marche/opportunites.html")


@pages_bp.route("/marches/sentiment")
@pages_bp.route("/<lang_code>/markets/sentiment")
def market_sentiment(lang_code=None):
    normalize_lang(lang_code)
    return render_template("marche/sentiment.html")


# =========================================================
# LEARN SIGNAL / REPLAY
# =========================================================
@pages_bp.route("/learn/signal/<int:signal_id>")
@pages_bp.route("/<lang_code>/learn/signal/<int:signal_id>")
def learn_signal(signal_id, lang_code=None):
    normalize_lang(lang_code)

    signal = Signal.query.get_or_404(signal_id)

    replay = {
        "id": signal.id,
        "symbol": signal.asset or "BTCUSD",
        "timeframe": str(signal.timeframe or "15m"),
        "direction": (signal.action or "BUY").upper(),
        "entry_price": signal.entry_price,
        "stop_loss": signal.stop_loss,
        "take_profit": signal.take_profit,
        "result": (signal.status or "OPEN").upper(),
        "market_context": signal.reason or "Aucune analyse de contexte disponible.",
        "post_analysis": signal.reason or "Aucune analyse post-trade disponible.",
        "created_at": signal.created_at,
        "confidence": signal.confidence if signal.confidence is not None else 50,
        "trend": signal.market_trend or "Neutre",
        "risk_reward": signal.risk_reward or "—",
    }

    return render_template("replay.html", replay=replay)




# =========================================================
# WHALE INTELLIGENCE
# =========================================================
@pages_bp.route("/marche/whales")
@pages_bp.route("/<lang_code>/markets/whales")
def whales(lang_code=None):
    normalize_lang(lang_code)

    service = WhaleTrackingService()

    asset = (request.args.get("asset", "") or "").strip().upper()
    impact = (request.args.get("impact", "") or "").strip().lower()
    direction = (request.args.get("direction", "") or "").strip().lower()

    try:
        limit = int(request.args.get("limit", 12))
    except (TypeError, ValueError):
        limit = 12

    if limit < 1:
        limit = 1
    if limit > 50:
        limit = 50

    valid_assets = {"BTC", "ETH", "SOL", "USDT", "USDC"}
    valid_directions = {"inflow", "outflow", "transfer", "treasury"}

    asset_filter = asset if asset in valid_assets else None
    direction_filter = direction if direction in valid_directions else None
    only_high_impact = impact == "high"

    whale_alerts = service.get_whale_alerts_dict(
        asset=asset_filter,
        only_high_impact=only_high_impact,
        direction=direction_filter,
        limit=limit,
    )

    snapshot = service.get_dashboard_snapshot()
    latest_high_impact = service.get_latest_high_impact(limit=5)

    active_filters = {
        "asset": asset_filter or "",
        "impact": "high" if only_high_impact else "",
        "direction": direction_filter or "",
        "limit": limit,
    }

    return render_template(
        "marche/whales.html",
        whale_alerts=whale_alerts,
        snapshot=snapshot,
        latest_high_impact=latest_high_impact,
        active_filters=active_filters,
    )
#---------------------------------------------------


