from flask import Blueprint, render_template, request
from app.models import Signal
pages_bp = Blueprint("pages", __name__)


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
from app.models import Signal

@pages_bp.route("/learn/signal/<int:signal_id>")
def learn_signal(signal_id):
    signal = Signal.query.get_or_404(signal_id)
    return render_template("learn_signal.html", signal=signal)