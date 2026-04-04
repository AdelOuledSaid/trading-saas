from flask import Flask
import stripe
import config

from app.extensions import db, login_manager, cache
from app.core.auth import load_user


def create_app():
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static"
    )

    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["SQLALCHEMY_DATABASE_URI"] = config.DATABASE_URL
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["REMEMBER_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["REMEMBER_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PREFERRED_URL_SCHEME"] = "https"

    db.init_app(app)
    login_manager.init_app(app)
    cache.init_app(app)

    stripe.api_key = config.STRIPE_SECRET_KEY
    login_manager.user_loader(load_user)

    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.billing import billing_bp
    from app.routes.webhook import webhook_bp
    from app.routes.pages import pages_bp
    from app.routes.signals import signals_bp
    from app.routes.admin import admin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(webhook_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(signals_bp)
    app.register_blueprint(admin_bp)

    with app.app_context():
        db.create_all()

    return app