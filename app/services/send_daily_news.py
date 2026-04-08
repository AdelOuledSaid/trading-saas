from app import create_app
from app.services.news_digest_service import prepare_digest_articles
from app.services.telegram_service import send_telegram_message


def build_custom_news_message(articles: list[dict]) -> str:
    if not articles:
        return ""

    lines = [
        "📰 <b>Velwolf News — Daily Market Update</b>",
        "",
        "📊 <b>Top actualités du jour :</b>",
        "",
    ]

    for i, article in enumerate(articles[:6], start=1):
        title = article.get("title", "Sans titre")
        description = article.get("description", "")
        source = article.get("source", "Source inconnue")

        if description:
            lines.append(
                f"{i}. <b>{title}</b>\n"
                f"   {description[:140]}...\n"
                f"   <i>Source : {source}</i>"
            )
        else:
            lines.append(
                f"{i}. <b>{title}</b>\n"
                f"   <i>Source : {source}</i>"
            )

        lines.append("")

    lines += [
        "📌 <b>Lecture marché</b> : sentiment global à surveiller sur BTC, ETH et actifs risk-on.",
        "",
        "⏰ <b>Mise à jour</b> : quotidienne",
        "⚠️ <i>Information de marché uniquement — DYOR</i>",
        "",
        "💎 <b>Velwolf Intelligence</b>",
    ]

    message = "\n".join(lines).strip()

    if len(message) > 3900:
        message = message[:3890] + "..."

    return message


def main():
    app = create_app()

    with app.app_context():
        articles = prepare_digest_articles(limit=6, max_age_hours=72)

        if not articles:
            print("⚠️ Aucune news trouvée")
            return

        message = build_custom_news_message(articles)
        ok = send_telegram_message(message)

        if ok:
            print("✅ Message news envoyé sur Telegram")
        else:
            print("❌ Échec envoi Telegram")


if __name__ == "__main__":
    main()