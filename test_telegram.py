import sys
import os

# Assure que Python trouve "app"
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from app import create_app

# Import corrects depuis ton projet
from app.services.telegram_dispatcher import (
    send_whale_alerts,
    send_liquidations_alerts,
)

from app.services.news_dispatcher import (
    send_daily_news,
    send_breaking_news,
)

# ⚠️ Optionnel : éviter envoi réel Telegram
from unittest.mock import patch


def fake_send_message_to_tier(tier, message):
    print("\n" + "=" * 80)
    print(f"TIER: {tier}")
    print("-" * 80)
    print(message)
    print("=" * 80 + "\n")
    return True


def run_tests():
    app = create_app()

    with app.app_context():

        print("\n🔥 TEST WHALES (VIP batch)")
        print("-" * 50)
        print(send_whale_alerts())

        print("\n💥 TEST LIQUIDATIONS (Premium + VIP batch)")
        print("-" * 50)
        print(send_liquidations_alerts())

        print("\n📰 TEST DAILY NEWS")
        print("-" * 50)
        print(send_daily_news("morning"))

        print("\n🚨 TEST BREAKING NEWS")
        print("-" * 50)

        fake_article = {
            "id": "test-1",
            "title": "BTC volatility spike",
            "url": "https://test.com",
            "source": "test",
        }

        print(send_breaking_news(fake_article))


# 🔒 Empêche envoi réel Telegram
with patch("app.services.telegram_service.send_message_to_tier", side_effect=fake_send_message_to_tier):
    run_tests()