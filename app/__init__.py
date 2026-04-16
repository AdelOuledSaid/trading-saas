import os

from flask import Flask, g, session, request, url_for
import stripe
import config
from flask_migrate import Migrate

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

migrate = Migrate()

SUPPORTED_LANGS = ["fr", "en", "es"]
DEFAULT_LANG = "fr"


def _is_true(value):
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _should_autostart_liquidations(app):
    """
    Auto-start safe:
    - activable via AUTO_START_LIQUIDATIONS=true
    - sur Render, démarre automatiquement par défaut
    - en debug local, évite le double démarrage du reloader Flask
    """
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

    # =========================
    # CONFIGURATION
    # =========================
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["SQLALCHEMY_DATABASE_URI"] = config.DATABASE_URL
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["RESEND_API_KEY"] = getattr(config, "RESEND_API_KEY", "")
    app.config["APP_BASE_URL"] = getattr(config, "APP_BASE_URL", "")

    # =========================
    # SECURITE
    # =========================
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["REMEMBER_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["REMEMBER_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PREFERRED_URL_SCHEME"] = "https"

    # =========================
    # INIT EXTENSIONS
    # =========================
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    cache.init_app(app)

    login_manager.user_loader(load_user)

    # =========================
    # STRIPE
    # =========================
    stripe.api_key = config.STRIPE_SECRET_KEY

    # =========================
    # JINJA FILTERS
    # =========================
    app.jinja_env.filters["explain_reason"] = explain_reason

    # =========================
    # LANGUE / TRADUCTION
    # =========================
    @app.before_request
    def set_language():
        lang = None

        if request.view_args:
            lang = request.view_args.get("lang_code")

        if lang in SUPPORTED_LANGS:
            session["lang"] = lang

        if "lang" not in session:
            cookie_lang = request.cookies.get("user_lang")
            if cookie_lang in SUPPORTED_LANGS:
                session["lang"] = cookie_lang

        if "lang" not in session:
            browser_lang = request.accept_languages.best_match(SUPPORTED_LANGS)
            session["lang"] = browser_lang or DEFAULT_LANG

        current_lang = session.get("lang", DEFAULT_LANG)

        if current_lang not in SUPPORTED_LANGS:
            current_lang = DEFAULT_LANG
            session["lang"] = DEFAULT_LANG

        g.current_lang = current_lang
        g.translations = load_translations(current_lang)

    # =========================
    # COOKIE LANGUE
    # =========================
    @app.after_request
    def persist_language_cookie(response):
        lang = session.get("lang", DEFAULT_LANG)
        response.set_cookie(
            "user_lang",
            lang,
            max_age=60 * 60 * 24 * 365,
            secure=True,
            httponly=False,
            samesite="Lax",
        )
        return response

    # =========================
    # AUTO-INJECTION LANG_CODE
    # =========================
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

    # =========================
    # URL HELPERS
    # =========================
    def switch_lang_url(lang: str) -> str:
        if lang not in SUPPORTED_LANGS:
            lang = DEFAULT_LANG

        if not request.endpoint:
            return url_for("main.home", lang_code=lang)

        view_args = dict(request.view_args or {})
        view_args["lang_code"] = lang

        try:
            return url_for(request.endpoint, **view_args)
        except Exception:
            return url_for("main.home", lang_code=lang)

    # =========================
    # JINJA GLOBALS
    # =========================
    @app.context_processor
    def inject_globals():
        from flask_login import current_user

        translations = getattr(g, "translations", {})
        current_lang = getattr(g, "current_lang", DEFAULT_LANG)

        return {
            "has_access": has_access,
            "get_plan_level": get_plan_level,
            "signal_limit_for_plan": signal_limit_for_plan,
            "user_plan": getattr(current_user, "plan", "free"),
            "current_lang": current_lang,
            "supported_langs": SUPPORTED_LANGS,
            "t": lambda key, fallback=None: translate(translations, key, fallback),
            "switch_lang_url": switch_lang_url,
            "pricing": get_pricing_data(current_lang),
        }

    # =========================
    # BLUEPRINTS
    # =========================
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

    app.register_blueprint(economic_calendar_bp)
    app.register_blueprint(token_unlocks_bp)
    app.register_blueprint(liquidations_bp)
    app.register_blueprint(open_interest_bp)

    # =========================
    # AUTO START LIQUIDATIONS
    # =========================
    if _should_autostart_liquidations(app):
        try:
            from app.services.liquidations_service import get_liquidations_service
            get_liquidations_service().start()
            print("[Liquidations] Auto-start enabled")
        except Exception as e:
            print(f"[Liquidations] Auto-start skipped: {e}")

    return app