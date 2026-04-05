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
🧠 <b>Setup</b> : {format_reason(signal)}

━━━━━━━━━━━━━━━━━━
⏱ <b>Timeframe</b> : {format_timeframe(signal)}
🧭 <b>Tendance</b> : {format_market_trend(signal)}
📦 <b>Type</b> : {format_signal_type(signal)}
🆔 <b>Trade ID</b> : {signal.trade_id or "-"}

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
🧠 <b>Setup</b> : {format_reason(signal)}

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
🧠 <b>Setup</b> : {format_reason(signal)}

━━━━━━━━━━━━━━━━━━{learn_block}
📌 <b>Statut</b> : 🔴 LOSS
⚠️ <i>Trade clôturé en perte</i>

💎 <b>Velwolef AI</b>
""".strip()


def send_telegram_message(message: str) -> None:
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        current_app.logger.warning("Telegram non configuré.")
        return

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        current_app.logger.info("TELEGRAM STATUS: %s", response.status_code)
        current_app.logger.info("TELEGRAM RESPONSE: %s", response.text)
    except Exception as e:
        current_app.logger.error("Erreur Telegram : %s", repr(e))