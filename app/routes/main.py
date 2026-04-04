from flask import Blueprint, render_template
from app.services.market_service import get_market_updates

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def home():
    market_updates = get_market_updates()
    return render_template("home.html", market_updates=market_updates)