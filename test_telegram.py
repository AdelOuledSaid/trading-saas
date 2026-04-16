from app import create_app

app = create_app()

with app.app_context():
    from app.services.telegram_service import send_message_to_tier

    print("PUBLIC:", send_message_to_tier("public", "TEST PUBLIC"))
    print("BASIC:", send_message_to_tier("basic", "TEST BASIC"))
    print("PREMIUM:", send_message_to_tier("premium", "TEST PREMIUM"))
    print("VIP:", send_message_to_tier("vip", "TEST VIP"))