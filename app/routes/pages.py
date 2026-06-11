from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from flask_login import current_user, login_required

from flask import current_app
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
    try:
        from app.services.opportunities_service import get_opportunities_cached
        opportunities = get_opportunities_cached()
    except Exception as e:
        current_app.logger.error("Opportunities service error: %s", e)
        opportunities = []

    dominant = opportunities[0] if opportunities else None
    return render_template(
        "marche/opportunites.html",
        opportunities=opportunities,
        dominant=dominant,
    )


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
# MINI COURSE
# =========================================================

@pages_bp.route("/learn/mini-course/<int:signal_id>")
@pages_bp.route("/<lang_code>/learn/mini-course/<int:signal_id>")
@login_required
def mini_course(signal_id, lang_code=None):
    normalize_lang(lang_code)

    signal = Signal.query.get_or_404(signal_id)

    rr = None
    if signal.entry_price and signal.stop_loss and signal.take_profit:
        risk   = abs(signal.entry_price - signal.stop_loss)
        reward = abs(signal.take_profit - signal.entry_price)
        rr = f"{reward/risk:.1f}" if risk > 0 else "-"

    asset  = signal.asset or "N/A"
    action = signal.action or "N/A"
    trend  = signal.market_trend or "-"
    reason = signal.reason or "No additional context provided for this trade."

    data = {
        "rr": rr or "-",
        "ai_summary": (
            f"{asset} {action} setup with {signal.confidence or 0:.0f}% confidence. "
            f"Entry at {signal.entry_price}, SL at {signal.stop_loss}, TP at {signal.take_profit}. "
            f"Market trend: {trend}."
        ),
        "reason": reason,
        "objective": (
            f"Target: {signal.take_profit} — R:R {rr or '-'}. "
            "Take profit at the defined structural level."
        ),
        "invalidation": (
            f"Stop loss at {signal.stop_loss}. "
            "Thesis invalidated if price closes beyond the stop level."
        ),
        "execution_plan": (
            f"Enter {action} on {signal.timeframe or 'N/A'} timeframe. "
            "Wait for candle confirmation before entry. "
            "Set stop loss immediately. Do not move SL against the position."
        ),
        "strengths": [
            f"Confidence score: {signal.confidence or 0:.0f}%",
            f"Clear entry at {signal.entry_price}",
            f"Defined risk: SL at {signal.stop_loss}",
            f"R:R ratio: {rr or '-'}",
        ],
        "risks": [
            "Market can reverse before reaching the target",
            "Low liquidity periods can cause slippage",
            f"Trend ({trend}) can shift unexpectedly",
            "News events can invalidate technical setups",
        ],
        "mistake_to_avoid": (
            "Do not move your stop loss to avoid a loss. "
            "Do not add to a losing position. "
            "Exit at your predefined stop if the thesis is invalidated."
        ),
    }

    return render_template(
        "learn/mini_course.html",
        signal=signal,
        data=data,
        current_lang=normalize_lang(lang_code)
    )


# =========================================================
# WHALE INTELLIGENCE
# =========================================================
# ── WHALE CACHE ──────────────────────────────────────────────
import time as _wtime
import threading as _wthread

_WC = {"ts": 0, "alerts": [], "snapshot": {}, "latest": []}
_WC_LOCK = _wthread.Lock()
_WC_LOADING = [False]


def _whale_bg_refresh():
    if _WC_LOADING[0]:
        return
    _WC_LOADING[0] = True
    try:
        svc = WhaleTrackingService()
        a = svc.get_whale_alerts_dict(limit=50)
        s = svc.get_dashboard_snapshot()
        l = svc.get_latest_high_impact(limit=5)
        with _WC_LOCK:
            _WC.update({"ts": _wtime.time(), "alerts": a, "snapshot": s, "latest": l})
    except Exception as e:
        import logging; logging.getLogger(__name__).error("whale bg: %s", e)
    finally:
        _WC_LOADING[0] = False


def _whale_ensure():
    with _WC_LOCK:
        age = _wtime.time() - _WC["ts"]
        has = bool(_WC["alerts"])
    if not has or age > 300:
        t = _wthread.Thread(target=_whale_bg_refresh, daemon=True)
        t.start()
        if not has:
            t.join(timeout=15)


@pages_bp.route("/marche/whales")
@pages_bp.route("/<lang_code>/markets/whales")
def whales(lang_code=None):
    normalize_lang(lang_code)

    asset     = (request.args.get("asset",     "") or "").strip().upper()
    impact    = (request.args.get("impact",    "") or "").strip().lower()
    direction = (request.args.get("direction", "") or "").strip().lower()

    try:
        limit = int(request.args.get("limit", 12))
    except (TypeError, ValueError):
        limit = 12
    limit = max(1, min(50, limit))

    asset_filter    = asset     if asset     in {"BTC","ETH","SOL","USDT","USDC"} else None
    direction_filter = direction if direction in {"inflow","outflow","transfer","treasury"} else None
    only_high_impact = impact == "high"

    _whale_ensure()

    with _WC_LOCK:
        all_alerts         = list(_WC["alerts"])
        snapshot           = dict(_WC["snapshot"])
        latest_high_impact = list(_WC["latest"])

    if asset_filter:
        all_alerts = [a for a in all_alerts if (a.get("asset") or "").upper() == asset_filter]
    if direction_filter:
        all_alerts = [a for a in all_alerts if (a.get("direction") or "").lower() == direction_filter]
    if only_high_impact:
        all_alerts = [a for a in all_alerts if "high" in (a.get("impact_level") or "").lower()]

    whale_alerts   = all_alerts[:limit]
    active_filters = {
        "asset":     asset_filter or "",
        "impact":    "high" if only_high_impact else "",
        "direction": direction_filter or "",
        "limit":     limit,
    }

    return render_template(
        "marche/whales.html",
        whale_alerts=whale_alerts,
        snapshot=snapshot,
        latest_high_impact=latest_high_impact,
        active_filters=active_filters,
    )

#---------------------------------------------------


@pages_bp.route("/robots.txt")
def robots_txt():
    return current_app.send_static_file("robots.txt")

@pages_bp.route("/signaux-crypto")
@pages_bp.route("/<lang_code>/signaux-crypto")
@pages_bp.route("/<lang_code>/crypto-signals")
def seo_crypto_signals(lang_code=None):
    current_lang = normalize_lang(lang_code)
    return render_template(
        "seo/crypto_signals.html",
        current_lang=current_lang
    )

@pages_bp.route("/<lang_code>/analyse-bitcoin")
def analyse_bitcoin(lang_code):
    return render_template("seo/analyse_bitcoin.html", current_lang=lang_code)

@pages_bp.route("/<lang_code>/resultats-trading")
def resultats_trading(lang_code):
    return render_template("seo/resultats_trading.html", current_lang=lang_code)

@pages_bp.route("/<lang_code>/trading-academy")
def trading_academy(lang_code):
    return render_template("seo/trading_academy.html", current_lang=lang_code)

@pages_bp.route("/<lang_code>/signaux-trading")
def signaux_trading(lang_code):
    return render_template("seo/signaux_trading.html", current_lang=lang_code)

@pages_bp.route("/<lang_code>/analyse-crypto")
def analyse_crypto(lang_code):
    return render_template("seo/analyse_crypto.html", current_lang=lang_code)


@pages_bp.route("/sitemap.xml")
def sitemap():
    return current_app.send_static_file("sitemap.xml")

@pages_bp.route("/payment-success")
def payment_success():
    return render_template("payment_success.html")