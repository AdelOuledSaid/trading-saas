from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from flask_login import current_user
from app.models import Signal

pages_bp = Blueprint("pages", __name__)


def user_is_pro():
    try:
        if not current_user.is_authenticated:
            return False

        possible_values = [
            getattr(current_user, "plan", None),
            getattr(current_user, "subscription_plan", None),
            getattr(current_user, "role", None),
        ]

        for value in possible_values:
            if value and str(value).lower() in ["pro", "premium", "vip"]:
                return True

        return False
    except Exception:
        return False


def academy_progress():
    return session.get(
        "academy_progress",
        {
            "level1": 35,
            "level2": 0,
            "certificate_ready": False,
        },
    )


@pages_bp.route("/mentions-legales")
def mentions_legales():
    return render_template("mentions_legales.html")


@pages_bp.route("/privacy")
def privacy():
    return render_template("privacy.html")


@pages_bp.route("/cgu")
def cgu():
    return render_template("cgu.html")


@pages_bp.route("/faq")
def faq_page():
    return render_template("faq.html")


@pages_bp.route("/contact")
def contact():
    return render_template("contact.html")


@pages_bp.route("/search")
def search_page():
    query = request.args.get("q", "")
    return render_template("search.html", query=query)


@pages_bp.route("/about")
def about():
    return render_template("about.html")


@pages_bp.route("/trading-lab")
def trading_lab():
    return render_template("trading_lab/index.html")


@pages_bp.route("/trading-lab/structure")
def lab_structure():
    return render_template("trading_lab/structure.html")


@pages_bp.route("/trading-lab/risk")
def lab_risk():
    return render_template("trading_lab/risk.html")


@pages_bp.route("/trading-lab/psychology")
def lab_psychology():
    return render_template("trading_lab/psychology.html")


@pages_bp.route("/marches/crypto")
def market_crypto():
    return render_template("marche/crypto.html")


@pages_bp.route("/marches/forex")
def market_forex():
    return render_template("marche/forex.html")


@pages_bp.route("/marches/opportunites")
def market_opportunities():
    return render_template("marche/opportunites.html")


@pages_bp.route("/marches/sentiment")
def market_sentiment():
    return render_template("marche/sentiment.html")


@pages_bp.route("/learn/signal/<int:signal_id>")
def learn_signal(signal_id):
    signal = Signal.query.get_or_404(signal_id)
    return render_template("learn_signal.html", signal=signal)


# =========================
# ACADEMY PRO
# =========================

@pages_bp.route("/academy")
def academy_index():
    return render_template(
        "academy/index.html",
        is_pro=user_is_pro(),
        academy_progress=academy_progress()
    )


@pages_bp.route("/academy/level-1")
def academy_level_1():
    return render_template(
        "academy/level1.html",
        is_pro=user_is_pro(),
        academy_progress=academy_progress()
    )


@pages_bp.route("/academy/level-2")
def academy_level_2():
    return render_template(
        "academy/level2.html",
        is_pro=user_is_pro(),
        academy_progress=academy_progress()
    )


@pages_bp.route("/academy/upgrade")
def academy_upgrade():
    return render_template("academy/upgrade.html")


@pages_bp.route("/academy/complete/<level>", methods=["POST"])
def academy_complete_level(level):
    progress = academy_progress()

    if level == "level1":
        progress["level1"] = 100
        progress["level2"] = max(progress.get("level2", 0), 10)

    elif level == "level2":
        progress["level2"] = 100
        progress["certificate_ready"] = True

    session["academy_progress"] = progress
    flash("Progression mise à jour.", "success")
    return redirect(url_for("pages.academy_index"))