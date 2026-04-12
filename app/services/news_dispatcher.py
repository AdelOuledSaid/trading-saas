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
    send_message_to_tier,
)


NEWS_LIMITS = {
    "public": 2,
    "basic": 2,
    "premium": 5,
    "vip": 999999,
}


NEWS_TITLES = {
    "public": "VelWolef Public Market News",
    "basic": "VelWolef Basic Daily News",
    "premium": "VelWolef Premium Market News",
    "vip": "VelWolef VIP Market Intelligence",
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
            "limit": "unlimited",
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

        dedup_key = news_digest_key(tier, today_str, slot, version="v1")

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
    Breaking news :
    - public : oui, mais une news très importante seulement si tu appelles cette fonction
    - basic : oui
    - premium : oui
    - vip : oui
    """
    if not article:
        _log_warning("[news_dispatcher] Breaking news vide.")
        return {}

    article_id = str(article.get("id", "")).strip() or None
    article_url = str(article.get("url", "")).strip() or None
    article_hash = build_article_fingerprint(article)

    results = {}

    for tier in ["public", "basic", "premium", "vip"]:
        message = build_breaking_news_message(article)
        dedup_key = breaking_news_key(tier, article_id=article_id, article_url=article_url)

        results[tier] = _send_news_message(
            tier=tier,
            message=message,
            dedup_key=dedup_key,
            content_ref=article_url or article_id,
            content_hash=article_hash,
            content_type="breaking_news",
        )

    return results