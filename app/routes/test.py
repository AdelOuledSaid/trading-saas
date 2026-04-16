from flask import Blueprint
from app.services.telegram_service import send_telegram_message

test_bp = Blueprint("test_bp", __name__)

@test_bp.route("/test-telegram")
def test_telegram():
    ok = send_telegram_message("TEST TELEGRAM OK")
    return f"Result: {ok}"