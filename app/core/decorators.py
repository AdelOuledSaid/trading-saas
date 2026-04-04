from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user

from app.services.stripe_service import sync_user_premium_status, user_has_plan


def plan_required(required_plan):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))

            sync_user_premium_status(current_user)

            if not user_has_plan(current_user, required_plan):
                flash(f"Accès réservé au plan {required_plan.upper()} ou supérieur.")
                return redirect(url_for("billing.pricing"))

            return f(*args, **kwargs)
        return decorated_function
    return decorator