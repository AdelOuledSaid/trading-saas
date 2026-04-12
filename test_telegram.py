from app import create_app
from app.services.telegram_service import send_message_to_tier

app = create_app()

with app.app_context():
    print(send_message_to_tier("public", "TEST PUBLIC OK"))
    print(send_message_to_tier("basic", "TEST BASIC OK"))
    print(send_message_to_tier("premium", "TEST PREMIUM OK"))
    print(send_message_to_tier("vip", "TEST VIP OK"))