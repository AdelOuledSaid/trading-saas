from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from flask import current_app

from app.models import Signal
from app.services.briefing_service import (
    ensure_daily_briefing,
    get_daily_briefing_for_plan,
    get_briefing_content_for_plan,
)
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
    build_vip_result_teaser_message,
    send_breaking_news_to_tier,
    send_message_to_tier,
)
from app.services.liquidations_service import get_liquidations_service
from app.services.whale_tracking_service import get_whale_tracking_service
from app.services.free_unlocks_service import FreeUnlocksService


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
        allow_morning_brief=True,
        allow_second_brief=False,
        daily_news_count=2,
        allow_breaking_news=True,
        include_learn_link=False,
        news_title="Velwolf Public Market News",
        news_intro="📢 Les actualités marché publiques les plus importantes du moment :",
    ),
    "basic": TierRules(
        tier="basic",
        signal_limit=3,
        allow_open_signals=True,
        allow_tp_sl_updates=True,
        allow_morning_brief=True,
        allow_second_brief=False,
        daily_news_count=3,
        allow_breaking_news=True,
        include_learn_link=False,
        news_title="Velwolf Basic Daily News",
        news_intro="📊 Les news essentielles pour les membres Basic :",
    ),
    "premium": TierRules(
        tier="premium",
        signal_limit=3,
        allow_open_signals=True,
        allow_tp_sl_updates=True,
        allow_morning_brief=True,
        allow_second_brief=True,
        daily_news_count=5,
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
        daily_news_count=5,
        allow_breaking_news=True,
        include_learn_link=True,
        news_title="Velwolf VIP Market Intelligence",
        news_intro="🚨 Flux VIP : news prioritaires, contexte marché et opportunités à surveiller :",
    ),
}


VALID_SLOTS = {"morning", "midday", "evening"}

PREMIUM_LIQUIDATION_DAILY_LIMIT = 5
VIP_WHALE_DAILY_LIMIT = 5
VIP_UNLOCK_DAILY_LIMIT = 3
PUBLIC_BASIC_WHALE_TEASER_DAILY_LIMIT = 3
PUBLIC_BASIC_LIQUIDATION_TEASER_DAILY_LIMIT = 3

PUBLIC_WIN_TEASER_DAILY_LIMIT = 2
PUBLIC_UNLOCK_TEASER_DAILY_LIMIT = 1
IMPORTANT_UNLOCK_THRESHOLD = 10_000_000


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


def _dedup_key(prefix: str, *parts) -> str:
    safe_parts = []
    for part in parts:
        safe_parts.append(str(part).replace(" ", "_").replace("/", "_").replace(":", "_"))
    return f"{prefix}:{':'.join(safe_parts)}"


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

    tier_normalized = (tier or "").lower()

    if tier_normalized == "vip":
        signature = "— <b>Velwolf Private Desk</b>"
    elif tier_normalized == "premium":
        signature = "— <b>Velwolf Intelligence Desk</b>"
    elif tier_normalized == "basic":
        signature = "— <b>Velwolf Market Desk</b>"
    else:
        signature = "— <b>Velwolf Market Desk</b>"

    header = f"<b>{title}</b>\n\n"
    body = (briefing_content or "").strip()
    footer = f"\n\n{signature}"

    message = header + body + footer

    if len(message) > 3900:
        message = message[:3890].rstrip() + "..."

    return message


def _get_plan_briefing_content(tier: str, fallback_content: str = "") -> str:
    plan_briefing = get_daily_briefing_for_plan(tier)
    if plan_briefing and getattr(plan_briefing, "content", None):
        return plan_briefing.content

    if fallback_content:
        return get_briefing_content_for_plan(fallback_content, tier)

    return ""


def _build_public_briefing_content(base_content: str) -> str:
    text = (base_content or "").strip()

    if not text:
        return (
            "🏛 <b>MARKET MORNING NOTE</b>\n\n"
            "<b>Régime du marché</b>\n"
            "• volatilité en reprise\n"
            "• flux sélectifs sur les actifs majeurs\n"
            "• absence de direction claire à court terme\n\n"
            "<b>Lecture desk</b>\n"
            "• zones techniques en cours de test\n"
            "• prudence avant validation des cassures\n"
            "• priorité à la gestion du risque\n\n"
            "🔒 <b>Accès limité</b>\n"
            "Le plan complet, les niveaux d’intervention et les scénarios de session sont réservés aux membres Premium et VIP."
        )

    clean_text = " ".join(text.split())
    teaser = clean_text[:500].rstrip()
    if len(clean_text) > 500:
        teaser += "..."

    return (
        "🏛 <b>MARKET MORNING NOTE</b>\n\n"
        "<b>Régime du marché</b>\n"
        f"{teaser}\n\n"
        "<b>Lecture desk</b>\n"
        "• priorité à la confirmation avant engagement\n"
        "• surveillance des réactions sur zones clés\n"
        "• attention aux accélérations sans relais de flux\n\n"
        "🔒 <b>Accès limité</b>\n"
        "Le plan complet, les niveaux d’intervention et les scénarios de session sont réservés aux membres Premium et VIP."
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


def _format_liquidation_message(event) -> str:
    return f"""
🚨 <b>Premium Liquidation Alert</b>

<b>{event.asset}</b> | {event.value_usd}
📍 {event.price} | ⚡ {event.impact}
📊 {event.market_bias} | 🏦 {event.exchange}
⏱ {event.time}

💎 <b>Premium Flow</b>
""".strip()


def _format_unlock_message(unlock: dict) -> str:
    unlock_date = unlock.get("date")
    if hasattr(unlock_date, "strftime"):
        unlock_date = unlock_date.strftime("%Y-%m-%d")

    value = unlock.get("value", 0) or 0
    try:
        value_text = f"${float(value):,.0f}"
    except Exception:
        value_text = str(value)

    risk_level = unlock.get("risk_level", "-")
    signal_level = unlock.get("signal_level", "-")
    token = unlock.get("token", "-")

    return f"""
🔓 <b>VIP Token Unlock</b>

🪙 <b>{token}</b> | {value_text}
📅 <b>Date</b> : {unlock_date}
⚠️ <b>Risk</b> : {risk_level} | 🧠 <b>Signal</b> : {signal_level}

💎 <b>VIP Intelligence</b>
""".strip()


def _format_unlock_teaser(unlock: dict) -> str:
    value = unlock.get("value", 0) or 0
    try:
        value_text = f"${float(value):,.0f}"
    except Exception:
        value_text = str(value)

    return f"""
🚨 <b>Token Unlock Important</b>

🪙 <b>{unlock.get("token", "-")}</b> | {value_text}
📅 <b>J-{unlock.get("days_until", "-")}</b>

⚠️ Pression potentielle sur le marché
👉 Analyse complète réservée aux membres <b>VIP</b>
""".strip()


def _format_liquidation_batch_message(events: list, tier: str = "premium") -> str:
    tier_label = "VIP" if (tier or "").strip().lower() == "vip" else "Premium"
    footer = "💎 <b>VIP Intelligence</b>" if tier_label == "VIP" else "💎 <b>Premium Flow</b>"

    lines = [f"🚨 <b>{tier_label} Liquidation Alert</b>"]

    for idx, event in enumerate(events, start=1):
        lines.append(
            f"<b>{idx}. {event.asset}</b> | {event.value_usd}\n"
            f"📍 {event.price} | ⚡ {event.impact} | 📊 {event.market_bias}\n"
            f"🏦 {event.exchange} | ⏱ {event.time}"
        )

    lines.append(footer)
    return "\n\n━━━━━━━━━━━━━━\n\n".join(lines)


def _format_whale_teaser(alert: dict) -> str:
    return f"""
🐋 <b>Whale Activity Detected</b>

💰 <b>{alert.get("asset", "-")}</b> | {alert.get("usd_value", "-")}
🔁 {alert.get("flow_type", "-")} | 🧠 {alert.get("bias", "-")}

⚡ Smart money en mouvement
👉 Full analysis réservé aux membres VIP
""".strip()


def _format_liquidation_teaser(event) -> str:
    return f"""
💥 <b>Liquidation Spike</b>

💰 <b>{event.asset}</b> | {event.value_usd}
📍 {event.price} | 📊 {event.market_bias}

⚡ Volatilité en hausse
👉 Accès complet Premium & VIP
""".strip()


def _format_single_whale_message(alert: dict) -> str:
    asset = alert.get("asset", "-")
    usd_value = alert.get("usd_value", "-")
    flow_type = alert.get("flow_type", "-")
    wallet_from = alert.get("wallet_from", "-")
    wallet_to = alert.get("wallet_to", "-")
    impact = alert.get("impact", "-")
    bias = alert.get("bias", "-")
    network = alert.get("network", "-")
    time_text = alert.get("time", "-")

    return f"""
🐋 <b>VIP Whale Flow</b>

<b>{asset}</b> | {usd_value}
🔁 <b>Flow</b> : {flow_type}
➡️ <b>From</b> : {wallet_from}
⬅️ <b>To</b> : {wallet_to}

⚡ <b>Impact</b> : {impact} | 🧠 <b>Bias</b> : {bias}
🌐 <b>Network</b> : {network} | ⏱ <b>Time</b> : {time_text}

💎 <b>VIP Intelligence</b>
""".strip()


def build_public_win_teaser_message(signal: Signal) -> str:
    asset = getattr(signal, "asset", None) or getattr(signal, "symbol", "ASSET")
    direction = getattr(signal, "side", None) or getattr(signal, "signal_type", "BUY")
    entry = (
        getattr(signal, "entry_price", None)
        or getattr(signal, "entry", None)
        or getattr(signal, "entry_value", None)
        or "-"
    )
    tp = (
        getattr(signal, "take_profit", None)
        or getattr(signal, "tp", None)
        or getattr(signal, "tp1", None)
        or getattr(signal, "target_price", None)
        or "-"
    )

    return f"""
🏆 <b>Signal gagnant clôturé</b>

💰 <b>{asset}</b> • {direction}
📍 <b>Entrée</b> : {entry} | 🎯 <b>TP</b> : {tp}

⏱ Signal déjà clôturé
🔒 Pour recevoir les signaux en direct avant fermeture, abonnez-vous en <b>Premium</b> ou <b>VIP</b>.
""".strip()


def send_public_signal_tp_teaser(signal: Signal) -> bool:
    if not signal:
        return False

    sent_today = count_sent_today("public_signal_tp_teaser", "public")
    if sent_today >= PUBLIC_WIN_TEASER_DAILY_LIMIT:
        _log_info("[telegram_dispatcher] Limite quotidienne TP teaser atteinte pour public.")
        return False

    key = signal_event_key(
        event_type="public_signal_tp_teaser",
        tier="public",
        signal_id=getattr(signal, "id", None),
        trade_id=getattr(signal, "trade_id", None),
    )

    return _send_text(
        tier="public",
        message=build_public_win_teaser_message(signal),
        content_type="public_signal_tp_teaser",
        dedup_key=key,
        content_ref=str(getattr(signal, "id", "")),
    )


def _send_public_basic_teasers(
    *,
    content_type: str,
    message: str,
    dedup_suffix: str,
    content_ref: str | None = None,
) -> dict:
    results = {}
    daily_limit = (
        PUBLIC_BASIC_WHALE_TEASER_DAILY_LIMIT
        if content_type == "whale_teaser"
        else PUBLIC_BASIC_LIQUIDATION_TEASER_DAILY_LIMIT
    )

    for tier in ["public", "basic"]:
        if count_sent_today(content_type, tier) >= daily_limit:
            _log_info(
                f"[telegram_dispatcher] Limite quotidienne teaser atteinte | type={content_type} | tier={tier}"
            )
            results[tier] = False
            continue

        results[tier] = _send_text(
            tier=tier,
            message=message,
            content_type=content_type,
            dedup_key=_dedup_key(content_type, tier, dedup_suffix),
            content_ref=content_ref,
        )

    return results


def send_morning_briefings() -> dict:
    briefing = ensure_daily_briefing()
    if not briefing or not getattr(briefing, "content", None):
        _log_warning("[telegram_dispatcher] Aucun briefing du matin disponible.")
        return {}

    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    slot = "morning"
    results = {}
    raw_content = briefing.content

    # =====================
    # PUBLIC
    # =====================
    if get_rules("public").allow_morning_brief:
        msg_public = format_briefing_message(
            briefing_content=_build_public_briefing_content(raw_content),
            title="Market Morning Note",
            tier="public",
        )

        key = briefing_key("morning_brief", "public", today_str, slot)

        results["public"] = _send_text(
            tier="public",
            message=msg_public,
            content_type="morning_brief",
            dedup_key=key,
        )

    # =====================
    # BASIC
    # =====================
    if get_rules("basic").allow_morning_brief:
        msg_basic = format_briefing_message(
            briefing_content=_get_plan_briefing_content("basic", raw_content),
            title="Market Brief",
            tier="basic",
        )

        key = briefing_key("morning_brief", "basic", today_str, slot)

        results["basic"] = _send_text(
            tier="basic",
            message=msg_basic,
            content_type="morning_brief",
            dedup_key=key,
        )

    # =====================
    # PREMIUM
    # =====================
    if get_rules("premium").allow_morning_brief:
        premium_content = (
            _get_plan_briefing_content("premium", raw_content)
            + "\n\n━━━━━━━━━━━━━━━━━━"
            + "\n<b>Plan de session</b>\n"
            + "• scénarios directionnels principaux\n"
            + "• zones d’intervention prioritaires\n"
            + "• validation requise avant exécution"
        )

        msg_premium = format_briefing_message(
            briefing_content=premium_content,
            title="Premium Market Note",
            tier="premium",
        )

        key = briefing_key("morning_brief", "premium", today_str, slot)

        results["premium"] = _send_text(
            tier="premium",
            message=msg_premium,
            content_type="morning_brief",
            dedup_key=key,
        )

    # =====================
    # VIP
    # =====================
    if get_rules("vip").allow_morning_brief:
        vip_content = (
            _get_plan_briefing_content("vip", raw_content)
            + "\n\n━━━━━━━━━━━━━━━━━━"
            + "\n<b>Desk execution framework</b>\n"
            + "• scénarios à haute probabilité\n"
            + "• gestion du timing d’entrée\n"
            + "• invalidations clés\n"
            + "• adaptation intraday selon flux"
        )

        msg_vip = format_briefing_message(
            briefing_content=vip_content,
            title="VIP Desk Opening Note",
            tier="vip",
        )

        key = briefing_key("morning_brief", "vip", today_str, slot)

        results["vip"] = _send_text(
            tier="vip",
            message=msg_vip,
            content_type="morning_brief",
            dedup_key=key,
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
    base_content = second_brief_content.strip()

    if get_rules("premium").allow_second_brief:
        msg_premium = format_briefing_message(
            briefing_content=_build_premium_second_content(base_content),
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
            briefing_content=_build_vip_second_content(base_content),
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
    articles = prepare_digest_articles(limit=4, max_age_hours=48)

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
    articles = prepare_digest_articles(limit=1, max_age_hours=3)

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

    results = {}

    results["public"] = send_public_signal_tp_teaser(signal)

    vip_key = signal_event_key(
        event_type="signal_tp",
        tier="vip",
        signal_id=getattr(signal, "id", None),
        trade_id=getattr(signal, "trade_id", None),
    )
    results["vip"] = _send_text(
        tier="vip",
        message=build_tp_telegram_message(signal),
        content_type="signal_tp",
        dedup_key=vip_key,
        content_ref=str(getattr(signal, "id", "")),
    )

    teaser_message = build_vip_result_teaser_message(signal)
    for tier in ["basic", "premium"]:
        teaser_key = signal_event_key(
            event_type="signal_tp_teaser",
            tier=tier,
            signal_id=getattr(signal, "id", None),
            trade_id=getattr(signal, "trade_id", None),
        )
        results[tier] = _send_text(
            tier=tier,
            message=teaser_message,
            content_type="signal_tp_teaser",
            dedup_key=teaser_key,
            content_ref=str(getattr(signal, "id", "")),
        )

    return results


def send_signal_sl(signal: Signal) -> dict:
    if not signal:
        _log_warning("[telegram_dispatcher] Signal SL vide.")
        return {}

    results = {}

    vip_key = signal_event_key(
        event_type="signal_sl",
        tier="vip",
        signal_id=getattr(signal, "id", None),
        trade_id=getattr(signal, "trade_id", None),
    )
    results["vip"] = _send_text(
        tier="vip",
        message=build_sl_telegram_message(signal),
        content_type="signal_sl",
        dedup_key=vip_key,
        content_ref=str(getattr(signal, "id", "")),
    )

    teaser_message = build_vip_result_teaser_message(signal)
    for tier in ["basic", "premium"]:
        teaser_key = signal_event_key(
            event_type="signal_sl_teaser",
            tier=tier,
            signal_id=getattr(signal, "id", None),
            trade_id=getattr(signal, "trade_id", None),
        )
        results[tier] = _send_text(
            tier=tier,
            message=teaser_message,
            content_type="signal_sl_teaser",
            dedup_key=teaser_key,
            content_ref=str(getattr(signal, "id", "")),
        )

    return results


def send_liquidations_alerts() -> dict:
    sent_today = count_sent_today("liquidation_alert", "premium")
    if sent_today >= PREMIUM_LIQUIDATION_DAILY_LIMIT:
        _log_info("[telegram_dispatcher] Limite quotidienne liquidations atteinte pour premium.")
        return {}

    service = get_liquidations_service()
    try:
        service.start()
    except Exception:
        pass

    events = service.get_events(only_high_impact=True, limit=10)
    filtered = [e for e in events if e.asset in {"BTC", "ETH", "SOL"}]

    if not filtered:
        _log_warning("[telegram_dispatcher] Aucune liquidation high impact exploitable.")
        return {}

    selected = filtered[:2]
    teaser_event = selected[0]
    results = _send_public_basic_teasers(
        content_type="liquidation_teaser",
        message=_format_liquidation_teaser(teaser_event),
        dedup_suffix=f"{teaser_event.asset}:{teaser_event.timestamp}",
        content_ref=f"{teaser_event.asset}:{teaser_event.timestamp}",
    )

    batch_ref = "|".join(f"{event.asset}:{event.timestamp}" for event in selected)
    batch_dedup_base = _dedup_key(
        "liquidation_alert_batch",
        *(f"{event.asset}:{event.side}:{event.timestamp}:{int(event.value_usd_number)}" for event in selected),
    )

    for tier in ["premium", "vip"]:
        results[tier] = _send_text(
            tier=tier,
            message=_format_liquidation_batch_message(selected, tier=tier),
            content_type="liquidation_alert",
            dedup_key=f"{batch_dedup_base}:{tier}",
            content_ref=batch_ref,
        )

    return results




#-------------------------------------------
#-----------------------------

def send_whale_alerts() -> dict:
    sent_today = count_sent_today("whale_alert", "vip")
    if sent_today >= VIP_WHALE_DAILY_LIMIT:
        _log_info("[telegram_dispatcher] Limite whale atteinte")
        return {}

    service = get_whale_tracking_service()
    alerts = service.get_latest_high_impact(limit=10)

    filtered = [
        a for a in alerts
        if (
            (a.get("usd_value_number", 0) or 0) >= 500_000
            and a.get("direction") in {"inflow", "outflow"}
            and a.get("exchange_related") is True
        )
    ]

    if not filtered:
        return {}

    # 🔥 Prend uniquement le plus important
    top = sorted(
        filtered,
        key=lambda x: float(x.get("usd_value_number", 0) or 0),
        reverse=True,
    )[0]

    # =====================
    # PUBLIC + BASIC TEASER
    # =====================
    teaser = f"""
🐋 <b>SMART MONEY DÉTECTÉ</b>

💰 <b>{top.get("asset")}</b> | {top.get("usd_value")}
⚡ {top.get("impact")} | 🧠 {top.get("bias")}

👉 Analyse complète réservée VIP
""".strip()

    results = _send_public_basic_teasers(
        content_type="whale_teaser",
        message=teaser,
        dedup_suffix=f"{top.get('asset')}:{top.get('timestamp')}",
    )

    # =====================
    # VIP MESSAGE PRO
    # =====================
    vip_msg = f"""
🐋 <b>VIP WHALE FLOW</b>

💰 <b>{top.get("asset")}</b> | {top.get("usd_value")}

🔁 Flow : {top.get("flow_type")}
➡️ From : {top.get("wallet_from")}
⬅️ To : {top.get("wallet_to")}

⚡ Impact : {top.get("impact")} | 🧠 Bias : {top.get("bias")}
🌐 {top.get("network")} | ⏱ {top.get("time")}

💎 <b>Smart Money Insight</b>
""".strip()

    results["vip"] = _send_text(
        tier="vip",
        message=vip_msg,
        content_type="whale_alert",
        dedup_key=f"whale:{top.get('asset')}:{top.get('timestamp')}",
    )

    return results










#----------------------------------------------

def send_token_unlocks_alerts() -> dict:
    service = FreeUnlocksService()
    unlocks = service.get_top_unlocks(days=7, limit=10)

    if not unlocks:
        return {}

    results = {}

    filtered = [
        u for u in unlocks
        if (u.get("value", 0) or 0) >= 1_000_000
        or u.get("risk_level") in ["high", "medium"]
    ]

    important_unlocks = [
        u for u in unlocks
        if (u.get("value", 0) or 0) >= IMPORTANT_UNLOCK_THRESHOLD
    ]

    if important_unlocks:
        important_unlocks = sorted(
            important_unlocks,
            key=lambda u: float(u.get("value", 0) or 0),
            reverse=True,
        )
        top_unlock = important_unlocks[0]
        sent_today = count_sent_today("unlock_teaser", "public")

        if sent_today < PUBLIC_UNLOCK_TEASER_DAILY_LIMIT:
            results["public"] = _send_text(
                tier="public",
                message=_format_unlock_teaser(top_unlock),
                content_type="unlock_teaser",
                dedup_key=f"unlock_teaser:{top_unlock.get('token')}:{top_unlock.get('date')}",
                content_ref=f"{top_unlock.get('token')}:{top_unlock.get('date')}",
            )
        else:
            results["public"] = False

    sent = 0
    filtered = sorted(
        filtered,
        key=lambda u: float(u.get("value", 0) or 0),
        reverse=True,
    )

    for u in filtered[:VIP_UNLOCK_DAILY_LIMIT]:
        ok = _send_text(
            tier="vip",
            message=_format_unlock_message(u),
            content_type="token_unlock",
            dedup_key=f"unlock:{u.get('token')}:{u.get('date')}",
            content_ref=f"{u.get('token')}:{u.get('date')}",
        )
        if ok:
            sent += 1

    results["vip"] = sent > 0
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
        "public": {
            "sent_today": count_sent_today("public_signal_tp_teaser", "public"),
            "limit": PUBLIC_WIN_TEASER_DAILY_LIMIT,
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

    if event == "liquidations":
        return send_liquidations_alerts()

    if event == "liquidation_teaser":
        return send_liquidations_alerts()

    if event == "whales":
        return send_whale_alerts()

    if event == "whale_teaser":
        return send_whale_alerts()

    if event == "unlocks":
        return send_token_unlocks_alerts()

    raise ValueError(f"Event type non supporté: {event_type}")