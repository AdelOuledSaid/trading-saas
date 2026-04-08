from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from flask import current_app

from app.services.market_service import get_market_updates
from app.services.telegram_service import send_telegram_message


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    while "  " in text:
        text = text.replace("  ", " ")
    return text


def parse_source_name(item: dict) -> str:
    source = item.get("source")

    if isinstance(source, dict):
        return normalize_text(source.get("name")) or "Source inconnue"

    if isinstance(source, str):
        return normalize_text(source) or "Source inconnue"

    return "Source inconnue"


def parse_published_at(value: Any) -> datetime | None:
    if not value:
        return None

    text = normalize_text(value)
    if not text:
        return None

    try:
        if text.endswith("Z"):
            text = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def normalize_article(item: dict) -> dict | None:
    title = normalize_text(item.get("title"))
    description = normalize_text(item.get("description") or item.get("summary"))
    url = normalize_text(item.get("url"))
    source = parse_source_name(item)
    image = normalize_text(item.get("image"))
    published_at = parse_published_at(item.get("publishedAt") or item.get("published_at"))

    if not title or not url:
        return None

    return {
        "title": title,
        "description": description,
        "url": url,
        "source": source,
        "image": image,
        "published_at": published_at,
    }


def article_unique_key(article: dict) -> str:
    title = normalize_text(article.get("title")).lower()
    url = normalize_text(article.get("url")).lower()
    return f"{title}|{url}"


def deduplicate_articles(articles: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique_articles: list[dict] = []

    for article in articles:
        key = article_unique_key(article)
        if key in seen:
            continue
        seen.add(key)
        unique_articles.append(article)

    return unique_articles


def filter_recent_articles(articles: list[dict], max_age_hours: int = 72) -> list[dict]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max_age_hours)

    recent_articles: list[dict] = []

    for article in articles:
        published_at = article.get("published_at")
        if published_at is None:
            recent_articles.append(article)
            continue

        if published_at >= cutoff:
            recent_articles.append(article)

    return recent_articles


def score_article(article: dict) -> int:
    text = f"{article.get('title', '')} {article.get('description', '')}".lower()
    score = 0

    important_keywords = [
        "bitcoin", "btc", "ethereum", "eth", "solana", "sol", "xrp",
        "gold", "nasdaq", "us100", "crypto", "etf", "sec", "regulation",
        "hack", "fraud", "lawsuit", "upgrade", "launch", "mainnet",
        "inflow", "outflow", "fed", "interest rates", "institutional",
        "blackrock",
    ]

    for keyword in important_keywords:
        if keyword in text:
            score += 2

    if "breaking" in text:
        score += 3

    if any(word in text for word in ["surge", "rally", "jump", "gain", "rise"]):
        score += 2

    if any(word in text for word in ["crash", "drop", "fall", "selloff", "decline"]):
        score += 2

    published_at = article.get("published_at")
    if isinstance(published_at, datetime):
        age_hours = (datetime.now(timezone.utc) - published_at).total_seconds() / 3600
        if age_hours <= 6:
            score += 3
        elif age_hours <= 24:
            score += 2
        elif age_hours <= 72:
            score += 1

    return score


def sort_articles_for_digest(articles: list[dict]) -> list[dict]:
    return sorted(
        articles,
        key=lambda a: (
            score_article(a),
            a.get("published_at") or datetime(1970, 1, 1, tzinfo=timezone.utc),
        ),
        reverse=True,
    )


def fetch_raw_news(limit: int = 12) -> list[dict]:
    try:
        raw_news = get_market_updates()
        if not raw_news:
            return []
        if isinstance(raw_news, list):
            return raw_news[:limit]
        current_app.logger.warning("Format inattendu pour get_market_updates: %s", type(raw_news))
        return []
    except Exception as exc:
        current_app.logger.error("Erreur récupération news digest: %s", repr(exc))
        return []


def prepare_digest_articles(limit: int = 6, max_age_hours: int = 72) -> list[dict]:
    raw_news = fetch_raw_news(limit=20)

    normalized: list[dict] = []
    for item in raw_news:
        article = normalize_article(item)
        if article:
            normalized.append(article)

    if not normalized:
        return []

    normalized = deduplicate_articles(normalized)
    normalized = filter_recent_articles(normalized, max_age_hours=max_age_hours)
    normalized = sort_articles_for_digest(normalized)

    prepared: list[dict] = []
    for article in normalized[:limit]:
        prepared.append({
            "title": article["title"],
            "description": article["description"],
            "url": article["url"],
            "source": article["source"],
            "image": article["image"],
        })

    return prepared


def truncate_text(text: str, max_len: int = 160) -> str:
    text = normalize_text(text)
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def news_emoji(article: dict) -> str:
    text = f"{article.get('title', '')} {article.get('description', '')}".lower()

    if any(word in text for word in ["etf", "institutional", "blackrock", "fund", "inflow"]):
        return "💰"
    if any(word in text for word in ["hack", "fraud", "exploit", "attack", "scam"]):
        return "🚨"
    if any(word in text for word in ["regulation", "sec", "lawsuit", "legal", "ban"]):
        return "⚖️"
    if any(word in text for word in ["upgrade", "launch", "mainnet", "integration"]):
        return "⚡"
    if any(word in text for word in ["surge", "rally", "jump", "rise", "gain"]):
        return "🟢"
    if any(word in text for word in ["drop", "fall", "crash", "selloff", "decline"]):
        return "🔻"

    return "📌"


def infer_market_bias(articles: list[dict]) -> str:
    score = 0

    positive_words = ["surge", "rise", "rally", "approval", "inflow", "bull", "growth", "launch", "upgrade"]
    negative_words = ["crash", "drop", "selloff", "hack", "fraud", "ban", "lawsuit", "outflow"]

    for article in articles:
        text = f"{article.get('title', '')} {article.get('description', '')}".lower()

        for word in positive_words:
            if word in text:
                score += 1

        for word in negative_words:
            if word in text:
                score -= 1

    if score >= 2:
        return "🟢 <b>Biais marché</b> : plutôt haussier"
    if score <= -2:
        return "🔻 <b>Biais marché</b> : plutôt baissier"
    return "⚖️ <b>Biais marché</b> : neutre à mixte"


def build_digest_message(articles: list[dict]) -> str:
    if not articles:
        return ""

    today = datetime.now().strftime("%d/%m/%Y")

    lines = [
        "📰 <b>Velwolf News — Daily Market Update</b>",
        "",
        f"📅 <b>{today}</b>",
        "",
        "📊 <b>Top actualités du jour :</b>",
        "",
    ]

    for i, article in enumerate(articles[:6], start=1):
        emoji = news_emoji(article)
        title = truncate_text(article.get("title", "Sans titre"), 110)
        description = truncate_text(article.get("description", ""), 150)
        source = article.get("source", "Source inconnue")

        if description:
            lines.append(
                f"{i}. {emoji} <b>{title}</b>\n"
                f"   {description}\n"
                f"   <i>Source : {source}</i>"
            )
        else:
            lines.append(
                f"{i}. {emoji} <b>{title}</b>\n"
                f"   <i>Source : {source}</i>"
            )

        lines.append("")

    lines.append(infer_market_bias(articles))
    lines.append("")
    lines.append("📌 <b>Lecture marché</b> : surveiller le momentum BTC, les flux institutionnels et la réaction des altcoins.")
    lines.append("")
    lines.append("⏰ <b>Mise à jour</b> : quotidienne")
    lines.append("⚠️ <i>Information de marché uniquement — DYOR</i>")
    lines.append("")
    lines.append("💎 <b>Velwolf Intelligence</b>")

    message = "\n".join(lines).strip()

    if len(message) > 3900:
        message = message[:3890].rstrip() + "..."

    return message


def send_news_digest(limit: int = 6, max_age_hours: int = 72) -> bool:
    articles = prepare_digest_articles(limit=limit, max_age_hours=max_age_hours)

    if not articles:
        current_app.logger.info("Aucune news valide pour le digest.")
        return False

    message = build_digest_message(articles)
    if not message:
        current_app.logger.info("Message digest vide.")
        return False

    ok = send_telegram_message(message)

    if ok:
        current_app.logger.info("Digest news envoyé avec succès.")
    else:
        current_app.logger.warning("Échec envoi digest news Telegram.")

    return ok