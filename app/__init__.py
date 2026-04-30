import os

from flask import Flask, g, session, request, url_for
import stripe
import config
from flask_migrate import Migrate
from flask import Flask, g, session, request, url_for, redirect
from app.extensions import db, login_manager, cache
from app.core.auth import load_user
from app.utils.explainer import explain_reason
from app.access import has_access, get_plan_level, signal_limit_for_plan
from app.utils.translator import load_translations, translate

from app.routes.economic_calendar import economic_calendar_bp
from app.routes.token_unlocks import token_unlocks_bp
from app.routes.liquidations import liquidations_bp
from app.routes.open_interest import open_interest_bp
from app.utils.pricing import get_pricing_data
from app.routes.test import test_bp
from app.routes.telegram import telegram_bp
from app.routes.technical_analysis import technical_analysis_bp
from app.routes.telegram_webhook import telegram_webhook_bp

from app.routes.academy_routes import academy_bp
from app.routes.manual_signal import manual_signal_bp
from app.routes.news_feed import news_feed_bp
from app.routes.market_ticker import market_ticker_bp
from app.routes.admin_trades import admin_trades_bp

migrate = Migrate()

# ✅ LANGUES SUPPORTÉES
SUPPORTED_LANGS = ["en", "fr", "es", "it", "de", "pt", "ru"]
DEFAULT_LANG = "en"


def _is_true(value):
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_plan(plan_value):
    plan = (plan_value or "basic").strip().lower()
    if plan not in {"basic", "premium", "vip"}:
        return "basic"
    return plan


def _should_autostart_liquidations(app):
    auto_start_env = os.environ.get("AUTO_START_LIQUIDATIONS")

    if auto_start_env is None:
        auto_start = os.environ.get("RENDER") == "true"
    else:
        auto_start = _is_true(auto_start_env)

    if not auto_start:
        return False

    if app.debug:
        return os.environ.get("WERKZEUG_RUN_MAIN") == "true"

    return True


def create_app():
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static"
    )

    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["SQLALCHEMY_DATABASE_URI"] = config.DATABASE_URL
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["RESEND_API_KEY"] = getattr(config, "RESEND_API_KEY", "")
    app.config["APP_BASE_URL"] = getattr(config, "APP_BASE_URL", "")

    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["REMEMBER_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["REMEMBER_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PREFERRED_URL_SCHEME"] = "https"

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    cache.init_app(app)

    login_manager.user_loader(load_user)

    stripe.api_key = config.STRIPE_SECRET_KEY

    app.jinja_env.filters["explain_reason"] = explain_reason

    # ✅ FORMAT PRIX
    def format_price(price):
        try:
            price = float(price)
            if price >= 1000:
                return f"{price:.2f}"
            elif price >= 1:
                return f"{price:.4f}"
            else:
                return f"{price:.6f}"
        except:
            return price

    app.jinja_env.filters["format_price"] = format_price

    # ✅ LANGUE (100% MANUELLE - PAS DE GEO / BROWSER)
    @app.before_request
    def force_lang():
        path = request.path

        if path.startswith((
            "/fr/", "/en/", "/es/", "/it/", "/de/", "/pt/", "/ru/",
            "/static/",
            "/api/",
            "/webhook",
            "/stripe-webhook",
            "/telegram",
            "/cron/",
            "/sitemap.xml",
            "/robots.txt",
            "/favicon.ico"
        )):
            return None

        if path == "/":
           return None

        return redirect("/fr" + path, code=301)
    @app.before_request
    def set_language():
        """
        Détection langue robuste.

        Priorité:
        1. /<lang_code>/ dans les routes Flask
        2. ?lang_code=de ou ?lang=de dans l'URL
        3. cookie user_lang
        4. session["lang"]
        5. DEFAULT_LANG
        """
        lang = None

        # 1) Langue depuis route /<lang_code>/...
        if request.view_args:
            lang = request.view_args.get("lang_code")

        # 2) Langue depuis query string
        if not lang:
            lang = request.args.get("lang_code") or request.args.get("lang")

        # 3) Langue depuis cookie
        if not lang:
            cookie_lang = request.cookies.get("user_lang")
            if cookie_lang in SUPPORTED_LANGS:
                lang = cookie_lang

        # 4) Langue depuis session
        if not lang:
            lang = session.get("lang")

        # 5) Sécurité / défaut
        if lang not in SUPPORTED_LANGS:
            lang = DEFAULT_LANG

        # Stockage unifié
        session["lang"] = lang
        g.current_lang = lang
        g.translations = load_translations(lang)

    # ✅ COOKIE LANGUE
    @app.after_request
    def persist_language_cookie(response):
        lang = session.get("lang", DEFAULT_LANG)
        response.set_cookie(
            "user_lang",
            lang,
            max_age=60 * 60 * 24 * 365,
            secure=not app.debug,  # FIX localhost
            httponly=False,
            samesite="Lax",
        )
        return response

    # ✅ AJOUT AUTOMATIQUE DU LANG_CODE DANS LES URLS
    @app.url_defaults
    def add_language_code(endpoint, values):
        if values is None:
            return

        if "lang_code" in values:
            return

        if not hasattr(g, "current_lang"):
            return

        try:
            rules = app.url_map._rules_by_endpoint.get(endpoint, [])
            if any("<lang_code>" in rule.rule for rule in rules):
                values["lang_code"] = g.current_lang
        except Exception:
            pass

    # ✅ SWITCH LANGUE
    def switch_lang_url(lang: str) -> str:
        """
        Génère l'URL de changement de langue pour la page actuelle.

        Si la route actuelle possède <lang_code>, on remplace lang_code.
        Si la route actuelle n'a pas <lang_code>, on garde la même page avec ?lang_code=xx.
        """
        if lang not in SUPPORTED_LANGS:
            lang = DEFAULT_LANG

        if not request.endpoint:
            return url_for("main.home", lang_code=lang)

        view_args = dict(request.view_args or {})

        try:
            rules = app.url_map._rules_by_endpoint.get(request.endpoint, [])
            has_lang_code = any("<lang_code>" in rule.rule for rule in rules)

            if has_lang_code:
                view_args["lang_code"] = lang
                return url_for(request.endpoint, **view_args)

            # Route sans <lang_code> : on garde endpoint + query param.
            query_args = dict(request.args)
            query_args["lang_code"] = lang
            return url_for(request.endpoint, **view_args, **query_args)

        except Exception:
            return url_for("main.home", lang_code=lang)

    # ✅ VARIABLES GLOBALES JINJA
    @app.context_processor
    def inject_globals():
        from flask_login import current_user

        translations = getattr(g, "translations", {})
        current_lang = getattr(g, "current_lang", DEFAULT_LANG)

        is_logged_in = getattr(current_user, "is_authenticated", False)

        if is_logged_in:
            user_plan = _normalize_plan(getattr(current_user, "plan", "basic"))
        else:
            user_plan = "guest"

        return {
            "has_access": has_access,
            "get_plan_level": get_plan_level,
            "signal_limit_for_plan": signal_limit_for_plan,
            "is_logged_in": is_logged_in,
            "user_plan": user_plan,
            "is_guest": user_plan == "guest",
            "is_basic": user_plan == "basic",
            "is_premium": user_plan == "premium",
            "is_vip": user_plan == "vip",
            "has_level1_access": user_plan in {"basic", "premium", "vip"},
            "has_academy_plus": user_plan in {"premium", "vip"},
            "current_lang": current_lang,
            "supported_langs": SUPPORTED_LANGS,
            "t": lambda key, fallback=None: translate(translations, key, fallback),
            "switch_lang_url": switch_lang_url,
            "pricing": get_pricing_data(current_lang),
        }

    # ✅ BLUEPRINTS
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.billing import billing_bp
    from app.routes.webhook import webhook_bp
    from app.routes.stripe_webhook import stripe_webhook_bp
    from app.routes.pages import pages_bp
    from app.routes.signals import signals_bp
    from app.routes.admin import admin_bp
    from app.routes.replay import replay_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(webhook_bp)
    app.register_blueprint(stripe_webhook_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(signals_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(replay_bp)
    app.register_blueprint(manual_signal_bp)
    app.register_blueprint(economic_calendar_bp)
    app.register_blueprint(token_unlocks_bp)
    app.register_blueprint(liquidations_bp)
    app.register_blueprint(open_interest_bp)
    app.register_blueprint(test_bp)
    app.register_blueprint(telegram_bp)
    app.register_blueprint(technical_analysis_bp)
    app.register_blueprint(telegram_webhook_bp)
    app.register_blueprint(news_feed_bp)
    app.register_blueprint(academy_bp)
    app.register_blueprint(market_ticker_bp)
    app.register_blueprint(admin_trades_bp)
    # ✅ AUTO START LIQUIDATIONS
    if _should_autostart_liquidations(app):
        try:
            from app.services.liquidations_service import get_liquidations_service
            get_liquidations_service().start()
            print("[Liquidations] Auto-start enabled")
        except Exception as e:
            print(f"[Liquidations] Auto-start skipped: {e}")

    return app