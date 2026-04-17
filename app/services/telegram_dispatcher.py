from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from flask import current_app

from app.models import Signal
from app.services.briefing_service import ensure_daily_briefing
from app.services.news_digest_service import prepare_digest_articles
from app.services.telegram_dedup import (
    briefing_key,
    breaking_news_key,
    build_article_fingerprint,
    count_sent_today,
    dispatch_exists,
    dispatch_exists_by_hash,
    news_digest_key,
    record_dispatch,
    signal_event_key,
    signal_quota_remaining,
)
from app.services.telegram_service import (
    build_news_digest_message,
    build_signal_telegram_message,
    build_sl_telegram_message,
    build_tp_telegram_message,
    send_breaking_news_to_tier,
    send_message_to_tier,
)


@dataclass(frozen=True)
class TierRules:
    tier: str
    signal_limit: int
    allow_open_signals: bool
    allow_tp_sl_updates: bool
    allow_morning_brief: bool
    allow_second_brief: bool
    daily_news_count: int
    allow_breaking_news: bool
    include_learn_link: bool
    news_title: str
    news_intro: str


TIER_RULES = {
    "public": TierRules(
        tier="public",
        signal_limit=0,
        allow_open_signals=False,
        allow_tp_sl_updates=False,
        allow_morning_brief=False,
        allow_second_brief=False,
        daily_news_count=24,
        allow_breaking_news=True,
        include_learn_link=False,
        news_title="Velwolf Public Market News",
        news_intro="📢 Les actualités marché publiques les plus importantes du moment :",
    ),
    "basic": TierRules(
        tier="basic",
        signal_limit=5,
        allow_open_signals=True,
        allow_tp_sl_updates=True,
        allow_morning_brief=True,
        allow_second_brief=False,
        daily_news_count=24,
        allow_breaking_news=True,
        include_learn_link=False,
        news_title="Velwolf Basic Daily News",
        news_intro="📊 Les news essentielles pour les membres Basic :",
    ),
    "premium": TierRules(
        tier="premium",
        signal_limit=10,
        allow_open_signals=True,
        allow_tp_sl_updates=True,
        allow_morning_brief=True,
        allow_second_brief=True,
        daily_news_count=24,
        allow_breaking_news=True,
        include_learn_link=True,
        news_title="Velwolf Premium Market News",
        news_intro="📊 Les actualités premium du jour avec davantage de profondeur :",
    ),
    "vip": TierRules(
        tier="vip",
        signal_limit=999999,
        allow_open_signals=True,
        allow_tp_sl_updates=True,
        allow_morning_brief=True,
        allow_second_brief=True,
        daily_news_count=24,
        allow_breaking_news=True,
        include_learn_link=True,
        news_title="Velwolf VIP Market Intelligence",
        news_intro="🚨 Flux VIP : news prioritaires, contexte marché et opportunités à surveiller :",
    ),
}


VALID_SLOTS = {"morning", "midday", "evening"}


def get_rules(tier: str) -> TierRules:
    normalized = (tier or "").strip().lower()
    if normalized not in TIER_RULES:
        raise ValueError(f"Tier inconnu: {tier}")
    return TIER_RULES[normalized]


def get_paid_tiers() -> List[str]:
    return ["basic", "premium", "vip"]


def get_all_tiers() -> List[str]:
    return ["public", "basic", "premium", "vip"]


def tier_signal_limit(tier: str) -> int:
    return get_rules(tier).signal_limit


def _normalize_slot(slot: str) -> str:
    normalized = (slot or "").strip().lower()
    if normalized not in VALID_SLOTS:
        raise ValueError(f"Slot invalide: {slot}")
    return normalized


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


def _send_text(
    *,
    tier: str,
    message: str,
    content_type: str,
    dedup_key: str,
    content_ref: str | None = None,
    content_hash: str | None = None,
) -> bool:
    if not message:
        _log_warning(f"[telegram_dispatcher] Message vide ignoré pour {tier}")
        return False

    if dispatch_exists(dedup_key):
        _log_info(f"[telegram_dispatcher] Doublon ignoré par clé | tier={tier} | key={dedup_key}")
        return False

    if content_hash and dispatch_exists_by_hash(content_type, tier, content_hash):
        _log_info(f"[telegram_dispatcher] Doublon ignoré par hash | type={content_type} | tier={tier}")
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
        _log_info(f"[telegram_dispatcher] Envoyé | type={content_type} | tier={tier}")
    else:
        _log_warning(f"[telegram_dispatcher] Échec envoi | type={content_type} | tier={tier}")

    return ok


def _send_breaking_news(
    *,
    tier: str,
    article: dict,
    dedup_key: str,
    content_ref: str | None = None,
    content_hash: str | None = None,
) -> bool:
    if not article:
        _log_warning(f"[telegram_dispatcher] Breaking news vide ignorée pour {tier}")
        return False

    if dispatch_exists(dedup_key):
        _log_info(f"[telegram_dispatcher] Doublon ignoré par clé | tier={tier} | key={dedup_key}")
        return False

    if content_hash and dispatch_exists_by_hash("breaking_news", tier, content_hash):
        _log_info(f"[telegram_dispatcher] Doublon ignoré par hash | type=breaking_news | tier={tier}")
        return False

    ok = send_breaking_news_to_tier(tier=tier, article=article)

    if ok:
        record_dispatch(
            content_type="breaking_news",
            tier=tier,
            dedup_key=dedup_key,
            content_text=str(article.get("title", "")),
            content_ref=content_ref,
            content_hash=content_hash,
            status="sent",
        )
        _log_info(f"[telegram_dispatcher] Envoyé | type=breaking_news | tier={tier}")
    else:
        _log_warning(f"[telegram_dispatcher] Échec envoi | type=breaking_news | tier={tier}")

    return ok


def format_briefing_message(
    briefing_content: str,
    title: str,
    tier: str,
) -> str:
    signature = "💎 <b>Velwolf Private Desk</b>" if tier.lower() == "vip" else "💎 <b>Velwolf Intelligence</b>"

    header = f"🧠 <b>{title}</b>\n\n"
    tier_line = f"🏷 <b>Niveau</b> : {tier.upper()}\n\n"
    body = briefing_content.strip()
    footer = f"\n\n{signature}"

    message = header + tier_line + body + footer
    if len(message) > 3900:
        message = message[:3890].rstrip() + "..."
    return message


def _build_basic_morning_content(base_content: str) -> str:
    return (
        base_content[:900].strip()
        + "\n\n━━━━━━━━━━━━━━━━━━"
        + "\n📌 <b>Basic Focus</b>"
        + "\n- lecture simple du marché"
        + "\n- zones principales à surveiller"
        + "\n- prudence avant toute entrée"
    )


def _build_premium_morning_content(base_content: str) -> str:
    return (
        base_content.strip()
        + "\n\n━━━━━━━━━━━━━━━━━━"
        + "\n📊 <b>Premium Focus</b>"
        + "\n- lecture détaillée de la tendance"
        + "\n- actifs prioritaires"
        + "\n- zones de réaction importantes"
    )


def _build_vip_morning_content(base_content: str) -> str:
    return (
        base_content.strip()
        + "\n\n━━━━━━━━━━━━━━━━━━"
        + "\n🔒 <b>VIP Focus</b>"
        + "\n- zones de liquidité prioritaires"
        + "\n- actifs à surveiller en priorité"
        + "\n- lecture macro / momentum"
        + "\n- scénarios invalidation / continuation"
        + "\n- préparation desk pour opportunités rapides"
    )


def _build_premium_second_content(base_content: str) -> str:
    return (
        base_content.strip()
        + "\n\n━━━━━━━━━━━━━━━━━━"
        + "\n📍 <b>Premium Update</b>"
        + "\n- setups à garder sous surveillance"
        + "\n- attention aux cassures sans volume"
        + "\n- confirmation avant nouvelle exposition"
    )


def _build_vip_second_content(base_content: str) -> str:
    return (
        base_content.strip()
        + "\n\n━━━━━━━━━━━━━━━━━━"
        + "\n🔒 <b>VIP Opportunity Map</b>"
        + "\n- setups sous surveillance"
        + "\n- zones de réaction prioritaires"
        + "\n- momentum à confirmer"
        + "\n- attention aux faux breakouts"
        + "\n- ajustements rapides selon session"
    )


def send_morning_briefings() -> dict:
    briefing = ensure_daily_briefing()
    if not briefing or not getattr(briefing, "content", None):
        _log_warning("[telegram_dispatcher] Aucun briefing du matin disponible.")
        return {}

    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    slot = "morning"
    results = {}

    if get_rules("basic").allow_morning_brief:
        msg_basic = format_briefing_message(
            briefing_content=_build_basic_morning_content(briefing.content),
            title="Morning Brief",
            tier="basic",
        )
        key = briefing_key("morning_brief", "basic", today_str, slot)
        results["basic"] = _send_text(
            tier="basic",
            message=msg_basic,
            content_type="morning_brief",
            dedup_key=key,
            content_ref=f"{today_str}:{slot}",
        )

    if get_rules("premium").allow_morning_brief:
        msg_premium = format_briefing_message(
            briefing_content=_build_premium_morning_content(briefing.content),
            title="Morning Brief Premium",
            tier="premium",
        )
        key = briefing_key("morning_brief", "premium", today_str, slot)
        results["premium"] = _send_text(
            tier="premium",
            message=msg_premium,
            content_type="morning_brief",
            dedup_key=key,
            content_ref=f"{today_str}:{slot}",
        )

    if get_rules("vip").allow_morning_brief:
        msg_vip = format_briefing_message(
            briefing_content=_build_vip_morning_content(briefing.content),
            title="Morning Brief VIP",
            tier="vip",
        )
        key = briefing_key("morning_brief", "vip", today_str, slot)
        results["vip"] = _send_text(
            tier="vip",
            message=msg_vip,
            content_type="morning_brief",
            dedup_key=key,
            content_ref=f"{today_str}:{slot}",
        )

    return results


def send_second_briefings(
    second_brief_content: str,
    title: str = "Midday / Evening Brief",
    slot: str = "midday",
) -> dict:
    if not second_brief_content or not second_brief_content.strip():
        _log_warning("[telegram_dispatcher] Second briefing vide.")
        return {}

    slot = _normalize_slot(slot)
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    results = {}

    if get_rules("premium").allow_second_brief:
        msg_premium = format_briefing_message(
            briefing_content=_build_premium_second_content(second_brief_content),
            title=title,
            tier="premium",
        )
        key = briefing_key("second_brief", "premium", today_str, slot)
        results["premium"] = _send_text(
            tier="premium",
            message=msg_premium,
            content_type="second_brief",
            dedup_key=key,
            content_ref=f"{today_str}:{slot}",
        )

    if get_rules("vip").allow_second_brief:
        msg_vip = format_briefing_message(
            briefing_content=_build_vip_second_content(second_brief_content),
            title=title,
            tier="vip",
        )
        key = briefing_key("second_brief", "vip", today_str, slot)
        results["vip"] = _send_text(
            tier="vip",
            message=msg_vip,
            content_type="second_brief",
            dedup_key=key,
            content_ref=f"{today_str}:{slot}",
        )

    return results


def _slice_news_for_tier(articles: list[dict], tier: str) -> list[dict]:
    rules = get_rules(tier)
    limit = rules.daily_news_count
    if limit <= 0:
        return []
    return articles[:limit]


def send_daily_news(slot: str = "morning") -> dict:
    slot = _normalize_slot(slot)
    articles = prepare_digest_articles(limit=10, max_age_hours=72)

    if not articles:
        _log_warning("[telegram_dispatcher] Aucune news disponible.")
        return {}

    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    slot_label = {
        "morning": "matin",
        "midday": "midi",
        "evening": "soir",
    }[slot]

    results = {}

    for tier in get_all_tiers():
        rules = get_rules(tier)
        sliced = _slice_news_for_tier(articles, tier)
        if not sliced:
            continue

        message = build_news_digest_message(
            sliced,
            title=f"{rules.news_title} • {slot_label}",
            intro=rules.news_intro,
        )

        key = news_digest_key(tier, today_str, slot)
        results[tier] = _send_text(
            tier=tier,
            message=message,
            content_type="daily_news",
            dedup_key=key,
            content_ref=f"{today_str}:{slot}",
        )

    return results


def send_hourly_news() -> dict:
    """
    Envoie 1 news fraîche par heure sur tous les canaux autorisés.
    Déduplication automatique via breaking_news_key + hash contenu.
    """
    articles = prepare_digest_articles(limit=12, max_age_hours=6)

    if not articles:
        _log_warning("[telegram_dispatcher] Aucune news horaire disponible.")
        return {}

    results = {}

    article = articles[0]
    article_id = str(article.get("id", "")).strip() or None
    article_url = str(article.get("url", "")).strip() or None
    article_hash = build_article_fingerprint(article)

    for tier in get_all_tiers():
        rules = get_rules(tier)

        if not rules.allow_breaking_news:
            continue

        key = breaking_news_key(
            tier,
            article_id=article_id,
            article_url=article_url,
        )

        results[tier] = _send_breaking_news(
            tier=tier,
            article=article,
            dedup_key=key,
            content_ref=article_url or article_id,
            content_hash=article_hash,
        )

    return results


def send_breaking_news(article: dict) -> dict:
    if not article:
        _log_warning("[telegram_dispatcher] Breaking news vide.")
        return {}

    results = {}
    article_id = str(article.get("id", "")).strip() or None
    article_url = str(article.get("url", "")).strip() or None
    article_hash = build_article_fingerprint(article)

    for tier in get_all_tiers():
        rules = get_rules(tier)
        if not rules.allow_breaking_news:
            continue

        key = breaking_news_key(tier, article_id=article_id, article_url=article_url)
        results[tier] = _send_breaking_news(
            tier=tier,
            article=article,
            dedup_key=key,
            content_ref=article_url or article_id,
            content_hash=article_hash,
        )

    return results


def send_signal_open(signal: Signal) -> dict:
    if not signal:
        _log_warning("[telegram_dispatcher] Signal OPEN vide.")
        return {}

    message = build_signal_telegram_message(signal)
    results = {}

    for tier in get_paid_tiers():
        rules = get_rules(tier)

        if not rules.allow_open_signals:
            continue

        remaining = signal_quota_remaining(tier, rules.signal_limit)

        if remaining <= 0:
            _log_info(f"[telegram_dispatcher] Quota atteint pour {tier} | limit={rules.signal_limit}")
            results[tier] = False
            continue

        key = signal_event_key(
            event_type="signal_open",
            tier=tier,
            signal_id=getattr(signal, "id", None),
            trade_id=getattr(signal, "trade_id", None),
        )

        results[tier] = _send_text(
            tier=tier,
            message=message,
            content_type="signal_open",
            dedup_key=key,
            content_ref=str(getattr(signal, "id", "")),
        )

    return results


def send_signal_tp(signal: Signal) -> dict:
    if not signal:
        _log_warning("[telegram_dispatcher] Signal TP vide.")
        return {}

    message = build_tp_telegram_message(signal)
    results = {}

    for tier in get_paid_tiers():
        rules = get_rules(tier)
        if not rules.allow_tp_sl_updates:
            continue

        key = signal_event_key(
            event_type="signal_tp",
            tier=tier,
            signal_id=getattr(signal, "id", None),
            trade_id=getattr(signal, "trade_id", None),
        )

        results[tier] = _send_text(
            tier=tier,
            message=message,
            content_type="signal_tp",
            dedup_key=key,
            content_ref=str(getattr(signal, "id", "")),
        )

    return results


def send_signal_sl(signal: Signal) -> dict:
    if not signal:
        _log_warning("[telegram_dispatcher] Signal SL vide.")
        return {}

    message = build_sl_telegram_message(signal)
    results = {}

    for tier in get_paid_tiers():
        rules = get_rules(tier)
        if not rules.allow_tp_sl_updates:
            continue

        key = signal_event_key(
            event_type="signal_sl",
            tier=tier,
            signal_id=getattr(signal, "id", None),
            trade_id=getattr(signal, "trade_id", None),
        )

        results[tier] = _send_text(
            tier=tier,
            message=message,
            content_type="signal_sl",
            dedup_key=key,
            content_ref=str(getattr(signal, "id", "")),
        )

    return results


def send_signal_batch(signals: List[Signal], tier: str) -> dict:
    if not signals:
        _log_warning(f"[telegram_dispatcher] Aucun signal batch pour {tier}.")
        return {tier: False}

    rules = get_rules(tier)
    if not rules.allow_open_signals:
        _log_warning(f"[telegram_dispatcher] OPEN non autorisé pour {tier}.")
        return {tier: False}

    if rules.signal_limit >= 999999:
        selected = list(signals)
    else:
        remaining = signal_quota_remaining(tier, rules.signal_limit)
        if remaining <= 0:
            return {
                "tier": tier,
                "sent": 0,
                "requested": 0,
                "success": False,
                "reason": "quota_reached",
            }
        selected = list(signals)[:remaining]

    ok_count = 0

    for signal in selected:
        key = signal_event_key(
            event_type="signal_open",
            tier=tier,
            signal_id=getattr(signal, "id", None),
            trade_id=getattr(signal, "trade_id", None),
        )

        ok = _send_text(
            tier=tier,
            message=build_signal_telegram_message(signal),
            content_type="signal_open",
            dedup_key=key,
            content_ref=str(getattr(signal, "id", "")),
        )
        if ok:
            ok_count += 1

    return {
        "tier": tier,
        "sent": ok_count,
        "requested": len(selected),
        "success": ok_count == len(selected),
    }


def send_latest_signals_from_db() -> dict:
    open_signals = (
        Signal.query
        .filter_by(status="OPEN")
        .order_by(Signal.created_at.desc())
        .all()
    )

    if not open_signals:
        _log_warning("[telegram_dispatcher] Aucun signal OPEN en base.")
        return {}

    results = {}
    for tier in get_paid_tiers():
        results[tier] = send_signal_batch(open_signals, tier)

    return results


def get_today_signal_stats() -> dict:
    return {
        "basic": {
            "sent_today": count_sent_today("signal_open", "basic"),
            "limit": tier_signal_limit("basic"),
        },
        "premium": {
            "sent_today": count_sent_today("signal_open", "premium"),
            "limit": tier_signal_limit("premium"),
        },
        "vip": {
            "sent_today": count_sent_today("signal_open", "vip"),
            "limit": "unlimited",
        },
    }


def dispatch_event(
    event_type: str,
    signal: Optional[Signal] = None,
    article: Optional[dict] = None,
    second_brief_content: Optional[str] = None,
    slot: str = "morning",
) -> dict:
    event = (event_type or "").strip().lower()

    if event == "morning_brief":
        return send_morning_briefings()

    if event == "second_brief":
        return send_second_briefings(
            second_brief_content or "",
            slot=slot,
        )

    if event == "daily_news":
        return send_daily_news(slot=slot)

    if event == "hourly_news":
        return send_hourly_news()

    if event == "breaking_news":
        return send_breaking_news(article or {})

    if event == "signal_open":
        return send_signal_open(signal)

    if event == "signal_tp":
        return send_signal_tp(signal)

    if event == "signal_sl":
        return send_signal_sl(signal)

    raise ValueError(f"Event type non supporté: {event_type}")