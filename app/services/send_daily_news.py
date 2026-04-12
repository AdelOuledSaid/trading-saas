from app import create_app
from app.services.news_digest_service import prepare_digest_articles
from app.services.telegram_service import (
    send_daily_news_digest_to_tier,
    build_news_digest_message,
    send_message_to_tier,
)


def main():
    app = create_app()

    with app.app_context():
        articles = prepare_digest_articles(limit=6, max_age_hours=72)

        if not articles:
            print("⚠️ Aucune news trouvée")
            return

        basic_articles = articles[:3]
        premium_articles = articles[:6]

        basic_ok = send_daily_news_digest_to_tier("basic", basic_articles)

        premium_message = build_news_digest_message(
            premium_articles,
            title="VelWolf Premium News — Daily Market Update",
            intro="📊 Voici les actualités premium du jour avec plus de profondeur :",
        )
        premium_ok = send_message_to_tier("premium", premium_message)
        vip_ok = send_message_to_tier("vip", premium_message)

        print(f"Basic: {'OK' if basic_ok else 'FAIL'}")
        print(f"Premium: {'OK' if premium_ok else 'FAIL'}")
        print(f"VIP: {'OK' if vip_ok else 'FAIL'}")


if __name__ == "__main__":
    main()