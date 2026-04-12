import html
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
        "US100": "🇺🇸",
        "US500": "📊",
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


def build_learn_link(signal) -> str | None:
    signal_id = getattr(signal, "id", None)
    if not signal_id:
        return None
    return f"{get_site_url()}/learn/signal/{signal_id}"


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
    """
    Compatibilité avec ancien code.
    Envoie sur le canal public si défini, sinon sur Basic.
    """
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
    learn_block = (
        f'\n🎓 <a href="{learn_link}">Mini cours : comprendre ce signal</a>\n'
        if learn_link else ""
    )

    return f"""
🚨 <b>VELWOLEF SIGNAL</b>

{asset_icon} <b>{asset}</b> • {dir_icon} <b>{action}</b>

━━━━━━━━━━━━━━━━━━
💰 <b>Entrée</b> : {format_price(signal.entry_price)}
🛑 <b>SL</b> : {format_price(signal.stop_loss)}
🎯 <b>TP</b> : {format_price(signal.take_profit)}
⚖️ <b>RR</b> : {format_rr(signal)}

━━━━━━━━━━━━━━━━━━
🔥 <b>Confidence</b> : {conf_icon} {format_confidence(signal)}
🧠 <b>Setup</b> : {html.escape(format_reason(signal))}

━━━━━━━━━━━━━━━━━━
⏱ <b>Timeframe</b> : {html.escape(format_timeframe(signal))}
🧭 <b>Tendance</b> : {html.escape(format_market_trend(signal))}
📦 <b>Type</b> : {html.escape(format_signal_type(signal))}
🆔 <b>Trade ID</b> : {html.escape(str(signal.trade_id or "-"))}

━━━━━━━━━━━━━━━━━━{learn_block}
📌 <b>Statut</b> : 🟡 OPEN
🕒 <b>Heure</b> : {signal.created_at.strftime('%Y-%m-%d %H:%M:%S')} UTC

💎 <i>Velwolef AI Trading System</i>
""".strip()


def build_tp_telegram_message(signal) -> str:
    asset = (signal.asset or "").upper()
    action = (signal.action or "").upper()
    asset_icon = asset_emoji(asset)
    dir_icon = action_emoji(action)
    conf_icon = confidence_icon(signal)
    pnl = calculate_trade_pnl(signal)

    learn_link = build_learn_link(signal)
    learn_block = (
        f'\n🎓 <a href="{learn_link}">Revoir l’analyse de ce signal</a>\n'
        if learn_link else ""
    )

    return f"""
✅ <b>TAKE PROFIT TOUCHÉ</b>

{asset_icon} <b>{asset}</b> • {dir_icon} <b>{action}</b>

━━━━━━━━━━━━━━━━━━
💰 <b>Entrée</b> : {format_price(signal.entry_price)}
🎯 <b>TP atteint</b> : {format_price(signal.take_profit)}
💵 <b>PnL</b> : +{format_price(abs(pnl))}

━━━━━━━━━━━━━━━━━━
🔥 <b>Confidence initiale</b> : {conf_icon} {format_confidence(signal)}
🧠 <b>Setup</b> : {html.escape(format_reason(signal))}

━━━━━━━━━━━━━━━━━━{learn_block}
📌 <b>Statut</b> : 🟢 WIN
🏆 <i>Trade gagnant clôturé</i>

💎 <b>Velwolef AI</b>
""".strip()


def build_sl_telegram_message(signal) -> str:
    asset = (signal.asset or "").upper()
    action = (signal.action or "").upper()
    asset_icon = asset_emoji(asset)
    dir_icon = action_emoji(action)
    conf_icon = confidence_icon(signal)
    pnl = calculate_trade_pnl(signal)

    learn_link = build_learn_link(signal)
    learn_block = (
        f'\n🎓 <a href="{learn_link}">Comprendre pourquoi ce signal a échoué</a>\n'
        if learn_link else ""
    )

    return f"""
❌ <b>STOP LOSS TOUCHÉ</b>

{asset_icon} <b>{asset}</b> • {dir_icon} <b>{action}</b>

━━━━━━━━━━━━━━━━━━
💰 <b>Entrée</b> : {format_price(signal.entry_price)}
🛑 <b>SL atteint</b> : {format_price(signal.stop_loss)}
💵 <b>PnL</b> : -{format_price(abs(pnl))}

━━━━━━━━━━━━━━━━━━
🔥 <b>Confidence initiale</b> : {conf_icon} {format_confidence(signal)}
🧠 <b>Setup</b> : {html.escape(format_reason(signal))}

━━━━━━━━━━━━━━━━━━{learn_block}
📌 <b>Statut</b> : 🔴 LOSS
⚠️ <i>Trade clôturé en perte</i>

💎 <b>Velwolef AI</b>
""".strip()


def news_emoji(title: str, description: str = "") -> str:
    text = f"{title} {description}".lower()

    if any(word in text for word in ["etf", "institution", "blackrock", "fund", "inflow"]):
        return "💰"
    if any(word in text for word in ["hack", "scam", "fraud", "exploit", "stolen", "attack"]):
        return "🚨"
    if any(word in text for word in ["regulation", "sec", "law", "ban", "legal", "lawsuit"]):
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
    title: str = "Velwolef News — Daily Market Update",
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
    lines.append("💎 <b>Velwolef Intelligence</b>")

    message = "\n".join(lines).strip()

    if len(message) > 3900:
        message = message[:3890].rstrip() + "..."

    return message


def build_breaking_news_message(article: dict) -> str:
    title = html.escape(str(article.get("title", "Sans titre")))
    description = html.escape(truncate_text(str(article.get("description", "")), 220))
    source = html.escape(str(article.get("source", "Source inconnue")))
    url = str(article.get("url", "")).strip()

    emoji = news_emoji(article.get("title", ""), article.get("description", ""))

    lines = [
        "🚨 <b>BREAKING NEWS</b>",
        "",
        f"{emoji} <b>{title}</b>",
        "",
    ]

    if description:
        lines.append(description)
        lines.append("")

    lines.append(f"🗞 <b>Source</b> : {source}")

    if url:
        lines.append(f'🔗 <a href="{html.escape(url)}">Lire l’article</a>')

    lines.append("")
    lines.append("💎 <b>Velwolef Intelligence</b>")

    return "\n".join(lines).strip()


def send_daily_news_digest_to_tier(tier: str, articles: list[dict]) -> bool:
    message = build_news_digest_message(articles)
    if not message:
        current_app.logger.info("Aucune news à envoyer pour %s.", tier)
        return False
    return send_message_to_tier(tier=tier, message=message)


def send_breaking_news_to_tier(tier: str, article: dict) -> bool:
    message = build_breaking_news_message(article)
    return send_message_to_tier(tier=tier, message=message)