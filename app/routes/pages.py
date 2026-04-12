from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from flask_login import current_user, login_required
from app.models import Signal

pages_bp = Blueprint("pages", __name__)


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
# ACADEMY
# Premium + VIP only
# =========================

@pages_bp.route("/academy")
def academy_index():
    return render_template(
        "academy/index.html",
        is_pro=user_has_academy_access(),
        user_plan=get_user_plan(),
        academy_progress=academy_progress()
    )


@pages_bp.route("/academy/level-1")
def academy_level_1():
    return render_template(
        "academy/level1.html",
        is_pro=user_has_academy_access(),
        user_plan=get_user_plan(),
        academy_progress=academy_progress()
    )


@pages_bp.route("/academy/level-2")
def academy_level_2():
    return render_template(
        "academy/level2.html",
        is_pro=user_has_academy_access(),
        user_plan=get_user_plan(),
        academy_progress=academy_progress()
    )


@pages_bp.route("/academy/upgrade")
def academy_upgrade():
    # Si déjà Premium/VIP, on peut soit afficher la page,
    # soit rediriger vers l'academy. Ici on redirige.
    if user_has_academy_access():
        return redirect(url_for("pages.academy_index"))

    return render_template(
        "academy/upgrade.html",
        is_pro=False,
        user_plan=get_user_plan(),
        academy_progress=academy_progress()
    )


@pages_bp.route("/academy/complete/<level>", methods=["POST"])
@login_required
def academy_complete_level(level):
    if not user_has_academy_access():
        flash("Le parcours Academy complet est réservé aux membres Premium et VIP.", "warning")
        return redirect(url_for("pages.academy_upgrade"))

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