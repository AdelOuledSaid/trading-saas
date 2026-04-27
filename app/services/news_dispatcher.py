from __future__ import annotations

from datetime import datetime
from typing import List

from flask import current_app

from app.services.news_digest_service import prepare_digest_articles
from app.services.telegram_dedup import (
    build_article_fingerprint,
    breaking_news_key,
    count_sent_today,
    dispatch_exists,
    dispatch_exists_by_hash,
    news_digest_key,
    record_dispatch,
)
from app.services.telegram_service import (
    build_breaking_news_message,
    build_news_digest_message,
    send_breaking_news_to_tier,
    send_message_to_tier,
)


NEWS_LIMITS = {
    "public": 3,
    "basic": 3,
    "premium": 5,
    "vip": 5,
}


NEWS_TITLES = {
    "public": "Velwolf Public Market News",
    "basic": "Velwolf Basic Daily News",
    "premium": "Velwolf Premium Market News",
    "vip": "Velwolf VIP Market Intelligence",
}


NEWS_INTROS = {
    "public": "📢 Les actualités marché les plus importantes du moment :",
    "basic": "📊 Les news essentielles pour les membres Basic :",
    "premium": "📊 Les news Premium avec plus de contexte marché :",
    "vip": "🚨 Flux VIP : news prioritaires, contexte et opportunités desk :",
}


VALID_SLOTS = {"morning", "midday", "evening"}


def _log_info(message: str) -> None:
    try:
        current_app.logger.info(message)
    except Exception:
        print(message)


def _log_warning(message: str) -> None:
    try:
        current_app.logger.warning(message)
    except Exception:
        print(message)


def _normalize_slot(slot: str) -> str:
    slot = (slot or "").strip().lower()
    if slot not in VALID_SLOTS:
        raise ValueError(f"Slot invalide: {slot}")
    return slot


def _tier_daily_news_limit(tier: str) -> int:
    return NEWS_LIMITS.get((tier or "").lower(), 0)


def _slice_articles_for_tier(articles: List[dict], tier: str) -> List[dict]:
    limit = _tier_daily_news_limit(tier)
    if limit <= 0:
        return []
    if limit >= 999999:
        return list(articles)
    return list(articles)[:limit]



def _send_breaking_news_article(
    *,
    tier: str,
    article: dict,
    dedup_key: str,
    content_ref: str | None = None,
    content_hash: str | None = None,
) -> bool:
    """
    Envoie une breaking news en gardant l'image si l'article contient image.
    Garde le même système anti-doublon + record_dispatch.
    """
    if not article:
        _log_warning(f"[news_dispatcher] Article breaking vide ignoré pour {tier}")
        return False

    if dispatch_exists(dedup_key):
        _log_info(f"[news_dispatcher] Doublon ignoré par clé | tier={tier} | key={dedup_key}")
        return False

    if content_hash and dispatch_exists_by_hash("breaking_news", tier, content_hash):
        _log_info(f"[news_dispatcher] Doublon ignoré par hash | type=breaking_news | tier={tier}")
        return False

    ok = send_breaking_news_to_tier(tier, article)

    if ok:
        preview_text = build_breaking_news_message(article)
        record_dispatch(
            content_type="breaking_news",
            tier=tier,
            dedup_key=dedup_key,
            content_text=preview_text,
            content_ref=content_ref,
            content_hash=content_hash,
            status="sent",
        )
        _log_info(f"[news_dispatcher] Breaking envoyée avec image si disponible | tier={tier}")
    else:
        _log_warning(f"[news_dispatcher] Échec envoi breaking | tier={tier}")

    return ok


def _send_news_message(
    *,
    tier: str,
    message: str,
    dedup_key: str,
    content_ref: str | None = None,
    content_hash: str | None = None,
    content_type: str = "daily_news",
) -> bool:
    if not message:
        _log_warning(f"[news_dispatcher] Message vide ignoré pour {tier}")
        return False

    if dispatch_exists(dedup_key):
        _log_info(f"[news_dispatcher] Doublon ignoré par clé | tier={tier} | key={dedup_key}")
        return False

    if content_hash and dispatch_exists_by_hash(content_type, tier, content_hash):
        _log_info(f"[news_dispatcher] Doublon ignoré par hash | type={content_type} | tier={tier}")
        return False

    ok = send_message_to_tier(tier, message)

    if ok:
        record_dispatch(
            content_type=content_type,
            tier=tier,
            dedup_key=dedup_key,
            content_text=message,
            content_ref=content_ref,
            content_hash=content_hash,
            status="sent",
        )
        _log_info(f"[news_dispatcher] Envoyé | type={content_type} | tier={tier}")
    else:
        _log_warning(f"[news_dispatcher] Échec envoi | type={content_type} | tier={tier}")

    return ok


def _format_breaking_news_batch_message(articles: List[dict], tier: str) -> str:
    title = {
        "public": "🚨 <b>Public Breaking News</b>",
        "basic": "🚨 <b>Basic Breaking News</b>",
        "premium": "🚨 <b>Premium Breaking News</b>",
        "vip": "🚨 <b>VIP Breaking News</b>",
    }.get((tier or "").lower(), "🚨 <b>Breaking News</b>")

    blocks = []
    for index, article in enumerate(articles, start=1):
        single_message = build_breaking_news_message(article).strip()
        blocks.append(f"{index}.\n{single_message}")

    message = f"{title}\n\n" + "\n\n━━━━━━━━━━━━━━━━━━\n\n".join(blocks)
    if len(message) > 3900:
        message = message[:3890].rstrip() + "..."
    return message


def get_today_news_stats() -> dict:
    return {
        "public": {
            "sent_today": count_sent_today("daily_news", "public"),
            "limit": NEWS_LIMITS["public"],
        },
        "basic": {
            "sent_today": count_sent_today("daily_news", "basic"),
            "limit": NEWS_LIMITS["basic"],
        },
        "premium": {
            "sent_today": count_sent_today("daily_news", "premium"),
            "limit": NEWS_LIMITS["premium"],
        },
        "vip": {
            "sent_today": count_sent_today("daily_news", "vip"),
            "limit": NEWS_LIMITS["vip"],
        },
    }


def send_daily_news(slot: str = "morning") -> dict:
    """
    Envoie un digest news par tier, y compris public.
    Le système anti-doublon bloque le même slot deux fois dans la même journée.
    """
    slot = _normalize_slot(slot)
    articles = prepare_digest_articles(limit=10, max_age_hours=72)

    if not articles:
        _log_warning("[news_dispatcher] Aucune news disponible.")
        return {}

    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    slot_label = {
        "morning": "matin",
        "midday": "midi",
        "evening": "soir",
    }[slot]

    results = {}

    for tier in ["public", "basic", "premium", "vip"]:
        tier_articles = _slice_articles_for_tier(articles, tier)
        if not tier_articles:
            continue

        message = build_news_digest_message(
            tier_articles,
            title=f"{NEWS_TITLES[tier]} • {slot_label}",
            intro=NEWS_INTROS[tier],
        )

        dedup_key = news_digest_key(tier, today_str, slot, version="v2")

        results[tier] = _send_news_message(
            tier=tier,
            message=message,
            dedup_key=dedup_key,
            content_ref=f"{today_str}:{slot}",
            content_type="daily_news",
        )

    return results


def send_breaking_news(article: dict) -> dict:
    """
    Breaking news unitaire.
    Garde l'image si article["image"] existe, sinon envoie un message texte ultra pro.
    """
    if not article:
        _log_warning("[news_dispatcher] Breaking news vide.")
        return {}

    article_id = str(article.get("id", "")).strip() or None
    article_url = str(article.get("url", "")).strip() or None
    article_hash = build_article_fingerprint(article)

    results = {}

    for tier in ["public", "basic", "premium", "vip"]:
        dedup_key = breaking_news_key(tier, article_id=article_id, article_url=article_url)

        results[tier] = _send_breaking_news_article(
            tier=tier,
            article=article,
            dedup_key=dedup_key,
            content_ref=article_url or article_id,
            content_hash=article_hash,
        )

    return results


def send_breaking_news_batch(articles: List[dict]) -> dict:
    """
    Regroupe plusieurs breaking news en un seul message par tier.
    """
    cleaned_articles = [article for article in (articles or []) if article]
    if not cleaned_articles:
        _log_warning("[news_dispatcher] Aucun article breaking news à envoyer en batch.")
        return {}

    results = {}
    batch_ref = datetime.utcnow().strftime("%Y-%m-%d-%H")

    for tier in ["public", "basic", "premium", "vip"]:
        message = _format_breaking_news_batch_message(cleaned_articles, tier)
        first_article = cleaned_articles[0]
        first_article_id = str(first_article.get("id", "")).strip() or "batch"
        dedup_key = breaking_news_key(
            tier,
            article_id=f"batch:{first_article_id}:{batch_ref}",
            article_url=None,
        )

        results[tier] = _send_news_message(
            tier=tier,
            message=message,
            dedup_key=dedup_key,
            content_ref=f"breaking_batch:{batch_ref}",
            content_type="breaking_news_batch",
        )

    return results
