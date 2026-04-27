import html
import os
import requests
from flask import current_app
import config

from app.services.signal_service import calculate_trade_pnl


def format_price(value: float) -> str:
    try:
        value = float(value)
    except Exception:
        return str(value)

    if abs(value) >= 1000:
        return f"{value:,.2f}".replace(",", " ")
    if abs(value) >= 1:
        return f"{value:.2f}"
    return f"{value:.6f}".rstrip("0").rstrip(".")


def asset_emoji(asset: str) -> str:
    mapping = {
        "BTCUSD": "₿",
        "ETHUSD": "⟠",
        "SOLUSD": "🟣",
        "XRPUSD": "💧",
        "GOLD": "🥇",
        "XAUUSD": "🥇",
        "US100": "🇺🇸",
        "NAS100": "🇺🇸",
        "US500": "📊",
        "SPX500": "📊",
        "FRA40": "🇫🇷",
    }
    return mapping.get((asset or "").upper(), "📊")


def action_emoji(action: str) -> str:
    return "📈" if (action or "").upper() == "BUY" else "📉"


def format_confidence(signal) -> str:
    confidence = getattr(signal, "confidence", None)
    if confidence is None:
        return "N/A"

    try:
        return f"{float(confidence):.0f}%"
    except Exception:
        return str(confidence)


def confidence_icon(signal) -> str:
    confidence = getattr(signal, "confidence", 0) or 0
    try:
        confidence = float(confidence)
    except Exception:
        confidence = 0

    if confidence >= 80:
        return "🟢"
    if confidence >= 65:
        return "🟡"
    return "🔴"


def format_reason(signal) -> str:
    reason = getattr(signal, "reason", None)
    if not reason:
        return "Analyse technique automatique"
    return str(reason)


def format_timeframe(signal) -> str:
    timeframe = getattr(signal, "timeframe", None)
    return timeframe if timeframe else "-"


def format_signal_type(signal) -> str:
    signal_type = getattr(signal, "signal_type", None)
    return signal_type if signal_type else "-"


def format_market_trend(signal) -> str:
    trend = getattr(signal, "market_trend", None)
    if not trend:
        return "-"
    return str(trend).capitalize()


def format_rr(signal) -> str:
    rr = getattr(signal, "risk_reward", None)
    if rr is None:
        return "-"
    try:
        return f"{float(rr):.2f}"
    except Exception:
        return str(rr)


def get_site_url() -> str:
    site_url = getattr(config, "SITE_URL", None)
    if site_url:
        return site_url.rstrip("/")
    return "https://trading-saas-1.onrender.com"


def get_affiliate_link(name: str, fallback: str = "") -> str:
    """
    Lit un lien affiliation depuis config.py ou .env.
    Exemples .env :
    AFFILIATE_KRAKEN_LINK=https://...
    AFFILIATE_BYBIT_LINK=https://...
    """
    key = f"AFFILIATE_{name.upper()}_LINK"
    link = getattr(config, key, None) or os.getenv(key) or fallback
    return str(link).strip()


def build_execution_affiliate_block() -> str:
    kraken_link = get_affiliate_link("KRAKEN")
    bybit_link = get_affiliate_link("BYBIT")

    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━",
        "⚡ <b>EXECUTION DU SIGNAL</b>",
        "",
    ]

    if kraken_link:
        lines.extend([
            '🔐 <b>Mode standard</b> : plateforme régulée',
            f'👉 <a href="{html.escape(kraken_link, quote=True)}">Trader sur Kraken</a>',
            "",
        ])

    if bybit_link:
        lines.extend([
            '🚀 <b>Mode avancé</b> : levier / exécution rapide',
            f'👉 <a href="{html.escape(bybit_link, quote=True)}">Trader sur Bybit</a>',
            "",
        ])

    if not kraken_link and not bybit_link:
        return ""

    lines.extend([
        "⚠️ <i>Vérifie toujours la disponibilité et la conformité selon ton pays. Le trading comporte des risques.</i>",
    ])

    return "\n".join(lines)


def build_learn_link(signal) -> str | None:
    signal_id = getattr(signal, "id", None)
    if not signal_id:
        return None
    return f"{get_site_url()}/mini-course/signal/{signal_id}"


def get_telegram_channels() -> dict:
    return {
        "public": getattr(config, "TELEGRAM_PUBLIC_CHAT_ID", ""),
        "basic": getattr(config, "TELEGRAM_BASIC_CHAT_ID", ""),
        "premium": getattr(config, "TELEGRAM_PREMIUM_CHAT_ID", ""),
        "vip": getattr(config, "TELEGRAM_VIP_CHAT_ID", ""),
    }


def send_telegram_message_to_chat(
    chat_id: str,
    message: str,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = True,
) -> bool:
    if not getattr(config, "TELEGRAM_BOT_TOKEN", None):
        current_app.logger.warning("Telegram bot token manquant.")
        return False

    if not chat_id:
        current_app.logger.warning("Telegram chat_id manquant.")
        return False

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_web_page_preview,
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        current_app.logger.info("TELEGRAM [%s] STATUS: %s", chat_id, response.status_code)
        current_app.logger.info("TELEGRAM [%s] RESPONSE: %s", chat_id, response.text)
        return response.ok
    except Exception as e:
        current_app.logger.error("Erreur Telegram [%s] : %s", chat_id, repr(e))
        return False


def send_telegram_photo_to_chat(
    chat_id: str,
    photo_url: str,
    caption: str,
    parse_mode: str = "HTML",
) -> bool:
    if not getattr(config, "TELEGRAM_BOT_TOKEN", None):
        current_app.logger.warning("Telegram bot token manquant.")
        return False

    if not chat_id:
        current_app.logger.warning("Telegram chat_id manquant.")
        return False

    if not photo_url:
        current_app.logger.warning("Telegram photo_url manquant.")
        return False

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {
        "chat_id": chat_id,
        "photo": photo_url,
        "caption": caption[:1024],
        "parse_mode": parse_mode,
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        current_app.logger.info("TELEGRAM PHOTO [%s] STATUS: %s", chat_id, response.status_code)
        current_app.logger.info("TELEGRAM PHOTO [%s] RESPONSE: %s", chat_id, response.text)
        return response.ok
    except Exception as e:
        current_app.logger.error("Erreur Telegram photo [%s] : %s", chat_id, repr(e))
        return False


def send_message_to_tier(
    tier: str,
    message: str,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = True,
) -> bool:
    channels = get_telegram_channels()
    chat_id = channels.get(tier)
    return send_telegram_message_to_chat(
        chat_id=chat_id,
        message=message,
        parse_mode=parse_mode,
        disable_web_page_preview=disable_web_page_preview,
    )


def send_photo_to_tier(
    tier: str,
    photo_url: str,
    caption: str,
    parse_mode: str = "HTML",
) -> bool:
    channels = get_telegram_channels()
    chat_id = channels.get(tier)
    return send_telegram_photo_to_chat(
        chat_id=chat_id,
        photo_url=photo_url,
        caption=caption,
        parse_mode=parse_mode,
    )


def send_message_to_many_tiers(
    tiers: list[str],
    message: str,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = True,
) -> dict:
    results = {}
    for tier in tiers:
        results[tier] = send_message_to_tier(
            tier=tier,
            message=message,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
        )
    return results


def send_telegram_message(
    message: str,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = True
) -> bool:
    channels = get_telegram_channels()
    fallback_chat = channels.get("public") or channels.get("basic")
    return send_telegram_message_to_chat(
        chat_id=fallback_chat,
        message=message,
        parse_mode=parse_mode,
        disable_web_page_preview=disable_web_page_preview,
    )


def build_signal_telegram_message(signal) -> str:
    asset = (signal.asset or "").upper()
    action = (signal.action or "").upper()

    asset_icon = asset_emoji(asset)
    dir_icon = action_emoji(action)
    conf_icon = confidence_icon(signal)

    learn_link = build_learn_link(signal)

    confidence_value = getattr(signal, "confidence", 0) or 0
    try:
        confidence_value = float(confidence_value)
    except Exception:
        confidence_value = 0

    rr_value = getattr(signal, "risk_reward", None)
    try:
        rr_value_num = float(rr_value) if rr_value is not None else 0
    except Exception:
        rr_value_num = 0

    trend_text = format_market_trend(signal)
    setup_text = html.escape(format_reason(signal))
    timeframe_text = html.escape(format_timeframe(signal))
    signal_type_text = html.escape(format_signal_type(signal))
    trade_id_text = html.escape(str(signal.trade_id or "-"))

    if confidence_value >= 85 and rr_value_num >= 2:
        setup_badge = "🎯 <b>SNIPER SETUP</b>"
        urgency_line = "⚡ <b>Priority</b> : élevée"
        execution_line = "🧨 <b>Execution</b> : confirmation forte + timing agressif"
    elif confidence_value >= 75:
        setup_badge = "🔥 <b>HIGH CONVICTION SETUP</b>"
        urgency_line = "⚡ <b>Priority</b> : élevée"
        execution_line = "🎯 <b>Execution</b> : bon alignement marché"
    elif confidence_value >= 65:
        setup_badge = "📈 <b>ACTIVE SETUP</b>"
        urgency_line = "⚡ <b>Priority</b> : normale"
        execution_line = "🧭 <b>Execution</b> : attendre confirmation propre"
    else:
        setup_badge = "🛡 <b>WATCHLIST SETUP</b>"
        urgency_line = "⚡ <b>Priority</b> : sélective"
        execution_line = "👀 <b>Execution</b> : prudence, setup à surveiller"

    trend_lower = (trend_text or "").lower()
    if trend_lower in ["bullish", "uptrend", "haussier", "bull"]:
        bias_line = "🟢 <b>Market Bias</b> : bullish structure"
    elif trend_lower in ["bearish", "downtrend", "baissier", "bear"]:
        bias_line = "🔻 <b>Market Bias</b> : bearish structure"
    elif trend_text and trend_text != "-":
        bias_line = f"⚖️ <b>Market Bias</b> : {html.escape(trend_text)}"
    else:
        bias_line = "⚖️ <b>Market Bias</b> : neutral / mixed"

    learn_block = (
        f'\n🎓 <a href="{learn_link}">Voir le mini cours lié à ce setup</a>'
        if learn_link else ""
    )

    execution_block = build_execution_affiliate_block()

    message = f"""
{setup_badge}

{asset_icon} <b>{asset}</b> • {dir_icon} <b>{action}</b>

━━━━━━━━━━━━━━━━━━
💰 <b>Entry</b> : {format_price(signal.entry_price)}
🛑 <b>Stop Loss</b> : {format_price(signal.stop_loss)}
🎯 <b>Take Profit</b> : {format_price(signal.take_profit)}
⚖️ <b>Risk/Reward</b> : {format_rr(signal)}

━━━━━━━━━━━━━━━━━━
🔥 <b>Confidence</b> : {conf_icon} {format_confidence(signal)}
{urgency_line}
{execution_line}

━━━━━━━━━━━━━━━━━━
🧠 <b>Setup Logic</b> : {setup_text}
{bias_line}
⏱ <b>Timeframe</b> : {timeframe_text}
📦 <b>Type</b> : {signal_type_text}
🆔 <b>Trade ID</b> : {trade_id_text}

━━━━━━━━━━━━━━━━━━
📌 <b>Status</b> : OPEN
🕒 <b>Time</b> : {signal.created_at.strftime('%Y-%m-%d %H:%M:%S')} UTC{learn_block}
{execution_block}

💎 <b>Velwolf Private Desk</b>
""".strip()

    if len(message) > 3900:
        message = message[:3890].rstrip() + "..."

    return message


def build_tp_telegram_message(signal) -> str:
    asset = (signal.asset or "").upper()
    action = (signal.action or "").upper()

    asset_icon = asset_emoji(asset)
    dir_icon = action_emoji(action)
    conf_icon = confidence_icon(signal)

    pnl = calculate_trade_pnl(signal)
    learn_link = build_learn_link(signal)

    confidence_value = getattr(signal, "confidence", 0) or 0
    try:
        confidence_value = float(confidence_value)
    except Exception:
        confidence_value = 0

    rr_value = getattr(signal, "risk_reward", None)
    try:
        rr_value_num = float(rr_value) if rr_value is not None else 0
    except Exception:
        rr_value_num = 0

    setup_text = html.escape(format_reason(signal))
    timeframe_text = html.escape(format_timeframe(signal))
    signal_type_text = html.escape(format_signal_type(signal))
    trend_text = format_market_trend(signal)
    trade_id_text = html.escape(str(signal.trade_id or "-"))

    if confidence_value >= 85 and rr_value_num >= 2:
        result_badge = "🏆 <b>SNIPER TARGET HIT</b>"
        quality_line = "🎯 <b>Quality</b> : execution premium validée"
    elif confidence_value >= 75:
        result_badge = "✅ <b>HIGH CONVICTION WIN</b>"
        quality_line = "🔥 <b>Quality</b> : setup fort confirmé"
    else:
        result_badge = "✅ <b>TARGET REACHED</b>"
        quality_line = "📈 <b>Quality</b> : scénario respecté"

    trend_lower = (trend_text or "").lower()
    if trend_lower in ["bullish", "uptrend", "haussier", "bull"]:
        bias_line = "🟢 <b>Market Bias</b> : bullish structure respected"
    elif trend_lower in ["bearish", "downtrend", "baissier", "bear"]:
        bias_line = "🔻 <b>Market Bias</b> : bearish structure respected"
    elif trend_text and trend_text != "-":
        bias_line = f"⚖️ <b>Market Bias</b> : {html.escape(trend_text)}"
    else:
        bias_line = "⚖️ <b>Market Bias</b> : neutral / mixed"

    learn_block = (
        f'\n🎓 <a href="{learn_link}">Revoir l’analyse complète de ce trade</a>'
        if learn_link else ""
    )

    message = f"""
{result_badge}

{asset_icon} <b>{asset}</b> • {dir_icon} <b>{action}</b>

━━━━━━━━━━━━━━━━━━
💰 <b>Entry</b> : {format_price(signal.entry_price)}
🎯 <b>Target Hit</b> : {format_price(signal.take_profit)}
💵 <b>PnL</b> : +{format_price(abs(pnl))}
⚖️ <b>Risk/Reward</b> : {format_rr(signal)}

━━━━━━━━━━━━━━━━━━
🔥 <b>Initial Confidence</b> : {conf_icon} {format_confidence(signal)}
{quality_line}
📌 <b>Outcome</b> : objective reached cleanly

━━━━━━━━━━━━━━━━━━
🧠 <b>Setup Logic</b> : {setup_text}
{bias_line}
⏱ <b>Timeframe</b> : {timeframe_text}
📦 <b>Type</b> : {signal_type_text}
🆔 <b>Trade ID</b> : {trade_id_text}

━━━━━━━━━━━━━━━━━━
🏆 <b>Status</b> : WIN{learn_block}

💎 <b>Velwolf Intelligence</b>
""".strip()

    if len(message) > 3900:
        message = message[:3890].rstrip() + "..."

    return message


def build_sl_telegram_message(signal) -> str:
    asset = (signal.asset or "").upper()
    action = (signal.action or "").upper()

    asset_icon = asset_emoji(asset)
    dir_icon = action_emoji(action)
    conf_icon = confidence_icon(signal)

    pnl = calculate_trade_pnl(signal)
    learn_link = build_learn_link(signal)

    confidence_value = getattr(signal, "confidence", 0) or 0
    try:
        confidence_value = float(confidence_value)
    except Exception:
        confidence_value = 0

    rr_value = getattr(signal, "risk_reward", None)
    try:
        rr_value_num = float(rr_value) if rr_value is not None else 0
    except Exception:
        rr_value_num = 0

    setup_text = html.escape(format_reason(signal))
    timeframe_text = html.escape(format_timeframe(signal))
    signal_type_text = html.escape(format_signal_type(signal))
    trend_text = format_market_trend(signal)
    trade_id_text = html.escape(str(signal.trade_id or "-"))

    if confidence_value >= 85 and rr_value_num >= 2:
        result_badge = "⚠️ <b>SNIPER SETUP INVALIDATED</b>"
        discipline_line = "🛡 <b>Risk Control</b> : invalidation exécutée proprement"
    elif confidence_value >= 75:
        result_badge = "❌ <b>HIGH CONVICTION SETUP FAILED</b>"
        discipline_line = "🧯 <b>Risk Control</b> : perte contrôlée"
    else:
        result_badge = "❌ <b>RISK INVALIDATED</b>"
        discipline_line = "📉 <b>Risk Control</b> : scénario non confirmé"

    trend_lower = (trend_text or "").lower()
    if trend_lower in ["bullish", "uptrend", "haussier", "bull"]:
        bias_line = "🟢 <b>Market Bias</b> : bullish context failed to hold"
    elif trend_lower in ["bearish", "downtrend", "baissier", "bear"]:
        bias_line = "🔻 <b>Market Bias</b> : bearish context failed to extend"
    elif trend_text and trend_text != "-":
        bias_line = f"⚖️ <b>Market Bias</b> : {html.escape(trend_text)}"
    else:
        bias_line = "⚖️ <b>Market Bias</b> : neutral / mixed"

    learn_block = (
        f'\n🎓 <a href="{learn_link}">Comprendre pourquoi le setup a échoué</a>'
        if learn_link else ""
    )

    message = f"""
{result_badge}

{asset_icon} <b>{asset}</b> • {dir_icon} <b>{action}</b>

━━━━━━━━━━━━━━━━━━
💰 <b>Entry</b> : {format_price(signal.entry_price)}
🛑 <b>Stop Hit</b> : {format_price(signal.stop_loss)}
💵 <b>PnL</b> : -{format_price(abs(pnl))}
⚖️ <b>Risk/Reward</b> : {format_rr(signal)}

━━━━━━━━━━━━━━━━━━
🔥 <b>Initial Confidence</b> : {conf_icon} {format_confidence(signal)}
{discipline_line}
📌 <b>Outcome</b> : invalidation respected

━━━━━━━━━━━━━━━━━━
🧠 <b>Setup Logic</b> : {setup_text}
{bias_line}
⏱ <b>Timeframe</b> : {timeframe_text}
📦 <b>Type</b> : {signal_type_text}
🆔 <b>Trade ID</b> : {trade_id_text}

━━━━━━━━━━━━━━━━━━
⚠️ <b>Status</b> : LOSS{learn_block}

💎 <b>Velwolf Intelligence</b>
""".strip()

    if len(message) > 3900:
        message = message[:3890].rstrip() + "..."

    return message


def build_vip_result_teaser_message(signal) -> str:
    asset = (signal.asset or "").upper()
    action = (signal.action or "").upper()

    asset_icon = asset_emoji(asset)
    dir_icon = action_emoji(action)
    timeframe_text = html.escape(format_timeframe(signal))
    trade_id_text = html.escape(str(signal.trade_id or "-"))

    return f"""
🔒 <b>Trade Update Reserved</b>

{asset_icon} <b>{asset}</b> • {dir_icon} <b>{action}</b>

━━━━━━━━━━━━━━━━━━
⏱ <b>Timeframe</b> : {timeframe_text}
🆔 <b>Trade ID</b> : {trade_id_text}

━━━━━━━━━━━━━━━━━━
Le résultat final de ce trade est réservé aux membres <b>VIP</b>.

💎 <b>VIP Unlock</b>
• TP / SL en temps réel
• résultat complet
• PnL du trade
• suivi desk complet

🚀 <b>Upgrade requis pour voir la clôture</b>

💎 <b>Velwolf Intelligence</b>
""".strip()


def news_emoji(title: str, description: str = "") -> str:
    text = f"{title} {description}".lower()

    if any(word in text for word in ["etf", "institution", "blackrock", "fund", "inflow"]):
        return "💰"
    if any(word in text for word in ["hack", "scam", "fraud", "exploit", "stolen", "attack"]):
        return "🚨"
    if any(word in text for word in ["regulation", "sec", "law", "ban", "legal", "lawsuit", "clarity act"]):
        return "⚖️"
    if any(word in text for word in ["upgrade", "launch", "mainnet", "update", "integration"]):
        return "⚡"
    if any(word in text for word in ["bull", "surge", "rise", "rally", "jump", "gain"]):
        return "🟢"
    if any(word in text for word in ["drop", "fall", "crash", "down", "selloff", "decline"]):
        return "🔻"
    return "📌"


def infer_market_bias(articles: list[dict]) -> str:
    score = 0
    positive_words = ["surge", "rise", "rally", "approval", "inflow", "bull", "growth", "launch", "upgrade"]
    negative_words = ["crash", "drop", "selloff", "hack", "fraud", "ban", "lawsuit", "outflow"]

    for article in articles:
        title = str(article.get("title", ""))
        description = str(article.get("description", ""))
        text = f"{title} {description}".lower()

        for word in positive_words:
            if word in text:
                score += 1

        for word in negative_words:
            if word in text:
                score -= 1

    if score >= 2:
        return "🟢 <b>Bias marché</b> : plutôt haussier"
    if score <= -2:
        return "🔻 <b>Bias marché</b> : plutôt baissier"
    return "⚖️ <b>Bias marché</b> : neutre à mixte"


def truncate_text(text: str, max_len: int = 180) -> str:
    if not text:
        return ""
    text = " ".join(str(text).split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def build_news_digest_message(
    articles: list[dict],
    title: str = "Velwolf News — Daily Market Update",
    intro: str = "📊 Voici les actualités les plus importantes du moment :",
) -> str:
    if not articles:
        return ""

    lines = [
        f"📰 <b>{html.escape(title)}</b>",
        "",
        html.escape(intro),
        "",
    ]

    for idx, article in enumerate(articles[:6], start=1):
        article_title = html.escape(str(article.get("title", "Sans titre")))
        description = truncate_text(str(article.get("description", "")), 160)
        source = html.escape(str(article.get("source", "Source inconnue")))
        emoji = news_emoji(article.get("title", ""), article.get("description", ""))

        if description:
            lines.append(
                f"{idx}. {emoji} <b>{article_title}</b>\n"
                f"   {html.escape(description)}\n"
                f"   <i>Source : {source}</i>"
            )
        else:
            lines.append(
                f"{idx}. {emoji} <b>{article_title}</b>\n"
                f"   <i>Source : {source}</i>"
            )
        lines.append("")

    lines.append(infer_market_bias(articles))
    lines.append("")
    lines.append("⏰ <b>Mise à jour</b> : quotidienne")
    lines.append("⚠️ <i>Information de marché uniquement — DYOR</i>")
    lines.append("")
    lines.append("💎 <b>Velwolf Intelligence</b>")

    message = "\n".join(lines).strip()

    if len(message) > 3900:
        message = message[:3890].rstrip() + "..."

    return message



def build_breaking_context(title: str, description: str = "") -> dict:
    """
    Moteur léger de contexte pour news Telegram.
    Ne dépend d'aucun service externe afin de ne pas casser l'envoi.
    """
    raw_text = f"{title} {description}".lower()

    context = {
        "event": "MARKET EVENT",
        "assets": ["BTC", "GOLD"],
        "impact": [
            "Market sentiment may shift quickly",
            "Volatility can increase around confirmation",
        ],
        "desk": "Markets may react quickly if the headline is confirmed by follow-through.",
        "execution": [
            "Avoid chasing the first reaction",
            "Wait for confirmation on key levels",
        ],
        "bias": "⚖️ Neutral / Mixed",
    }

    if any(k in raw_text for k in ["war", "strike", "airstrike", "attack", "israel", "lebanon", "iran", "gaza", "ceasefire", "missile"]):
        context.update({
            "event": "GEO RISK",
            "assets": ["XAUUSD", "OIL", "BTC"],
            "impact": [
                "Risk-off sentiment can increase",
                "Safe-haven demand may support Gold",
                "Oil volatility can expand if tensions spread",
            ],
            "desk": "Geopolitical escalation can trigger rapid repricing across safe-havens, energy and high-beta assets.",
            "execution": [
                "Favor defensive positioning",
                "Monitor Gold and Oil reaction",
                "Avoid aggressive leverage during headline risk",
            ],
            "bias": "🔻 Risk-Off",
        })
        return context

    if any(k in raw_text for k in ["fed", "fomc", "rate", "rates", "inflation", "cpi", "ppi", "nfp", "payrolls", "treasury", "yield", "dollar"]):
        context.update({
            "event": "MACRO EVENT",
            "assets": ["USD", "NAS100", "BTC", "GOLD"],
            "impact": [
                "Macro volatility likely around repricing",
                "Rate expectations can move risk assets",
                "Dollar and yields remain key drivers",
            ],
            "desk": "Macro headlines can move liquidity expectations quickly, especially across indices, crypto and Gold.",
            "execution": [
                "Trade the confirmed reaction, not the first spike",
                "Watch USD and yields before entry",
                "Reduce size during high-impact releases",
            ],
            "bias": "⚖️ Macro Sensitive",
        })
        return context

    if any(k in raw_text for k in ["bitcoin", "btc", "ethereum", "eth", "crypto", "solana", "sol", "xrp", "etf", "blackrock", "sec"]):
        context.update({
            "event": "CRYPTO EVENT",
            "assets": ["BTC", "ETH", "TOTAL"],
            "impact": [
                "Crypto volatility can expand",
                "Sentiment may shift across majors",
                "Liquidity zones become high priority",
            ],
            "desk": "Crypto headlines can quickly affect momentum, liquidations and positioning across major assets.",
            "execution": [
                "Watch BTC reaction first",
                "Avoid chasing thin liquidity moves",
                "Confirm with volume and market structure",
            ],
            "bias": "⚖️ Crypto Volatility",
        })
        return context

    if any(k in raw_text for k in ["gold", "xauusd", "oil", "wti", "brent", "silver"]):
        context.update({
            "event": "COMMODITY EVENT",
            "assets": ["XAUUSD", "OIL", "USD"],
            "impact": [
                "Commodity volatility can increase",
                "Safe-haven and energy flows may rotate",
                "USD reaction remains important",
            ],
            "desk": "Commodity headlines can create fast repricing, especially when linked to macro or geopolitical risk.",
            "execution": [
                "Monitor breakout levels",
                "Avoid entries without confirmation",
                "Respect volatility expansion",
            ],
            "bias": "⚖️ Commodity Volatility",
        })

    return context


def build_breaking_news_message(article: dict) -> str:
    title_raw = truncate_text(str(article.get("title", "Sans titre")), 190)
    description_raw = truncate_text(str(article.get("description", "")), 170)
    source = html.escape(str(article.get("source", "Source inconnue")))
    url = str(article.get("url", "")).strip()

    context = build_breaking_context(title_raw, description_raw)

    title = html.escape(title_raw)
    description = html.escape(description_raw)

    lines = [
        f"🚨 <b>BREAKING — {html.escape(context['event'])}</b>",
        "",
        f"<b>{title}</b>",
    ]

    if description:
        lines.extend(["", f"📰 {description}"])

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━",
        "",
        "⚠️ <b>Market Impact</b>",
    ])

    for item in context["impact"][:3]:
        lines.append(f"• {html.escape(item)}")

    lines.extend([
        "",
        "📊 <b>Assets in Focus</b>",
        "• " + html.escape(" / ".join(context["assets"][:4])),
        "",
        "━━━━━━━━━━━━━━━━━━",
        "",
        "🧠 <b>Desk View</b>",
        html.escape(context["desk"]),
        "",
        f"📌 <b>Bias</b> : {html.escape(context['bias'])}",
    ])

    if context.get("execution"):
        lines.extend(["", "🎯 <b>Execution Notes</b>"])
        for item in context["execution"][:3]:
            lines.append(f"• {html.escape(item)}")

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━",
        "",
        f"🗞 <i>Source : {source}</i>",
    ])

    if url:
        lines.append(f'🔗 <a href="{html.escape(url, quote=True)}">Read more</a>')

    lines.extend([
        "",
        "🔒 <b>VIP Desk</b> : full positioning, levels & risk model.",
        "",
        "💎 <b>Velwolf Intelligence</b>",
    ])

    message = "\n".join(lines).strip()

    if len(message) > 3900:
        message = message[:3890].rstrip() + "..."

    return message



def build_watcher_style_caption(article: dict) -> str:
    """
    Caption ultra pro pour les breaking news avec image.
    Limite Telegram sendPhoto caption : 1024 caractères.
    """
    title_raw = truncate_text(str(article.get("title", "Sans titre")), 135)
    description_raw = truncate_text(str(article.get("description", "")), 95)

    context = build_breaking_context(title_raw, description_raw)

    title = html.escape(title_raw)
    description = html.escape(description_raw)

    lines = [
        f"🚨 <b>BREAKING — {html.escape(context['event'])}</b>",
        "",
        f"<b>{title}</b>",
    ]

    if description:
        lines.extend(["", f"📰 {description}"])

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━",
        "",
        "⚠️ <b>Impact</b>",
    ])

    for item in context["impact"][:2]:
        lines.append(f"• {html.escape(item)}")

    lines.extend([
        "",
        "📊 <b>Focus</b>",
        "• " + html.escape(" / ".join(context["assets"][:3])),
        "",
        "🧠 <b>Desk</b>",
        html.escape(context["desk"]),
        "",
        "🔒 <b>VIP → Full strategy</b>",
        "💎 <b>@Velwolf</b>",
    ])

    caption = "\n".join(lines).strip()

    if len(caption) > 1024:
        caption = caption[:1014].rstrip() + "..."

    return caption



def send_breaking_news_to_tier(tier: str, article: dict) -> bool:
    image_url = str(article.get("image", "")).strip()
    if image_url:
        caption = build_watcher_style_caption(article)
        return send_photo_to_tier(tier=tier, photo_url=image_url, caption=caption)

    message = build_breaking_news_message(article)
    return send_message_to_tier(tier=tier, message=message)


def send_daily_news_digest_to_tier(tier: str, articles: list[dict]) -> bool:
    message = build_news_digest_message(articles)
    if not message:
        current_app.logger.info("Aucune news à envoyer pour %s.", tier)
        return False
    return send_message_to_tier(tier=tier, message=message)
