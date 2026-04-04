import requests
from flask import current_app
import config


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
    return mapping.get(asset.upper(), "📊")


def action_emoji(action: str) -> str:
    return "📈" if action.upper() == "BUY" else "📉"


def build_signal_telegram_message(signal) -> str:
    asset = signal.asset.upper()
    action = signal.action.upper()
    asset_icon = asset_emoji(asset)
    dir_icon = action_emoji(action)

    return f"""
🚨 <b>NOUVEAU SIGNAL PREMIUM</b>

💎 <b>TradingSignals Premium</b>

{asset_icon} <b>Actif :</b> {asset}
{dir_icon} <b>Direction :</b> {action}

🆔 <b>Trade ID :</b> {signal.trade_id or "-"}
💰 <b>Entrée :</b> {format_price(signal.entry_price)}
🛑 <b>Stop Loss :</b> {format_price(signal.stop_loss)}
🎯 <b>Take Profit :</b> {format_price(signal.take_profit)}

📌 <b>Statut :</b> 🟡 OPEN
🕒 <b>Heure :</b> {signal.created_at.strftime('%Y-%m-%d %H:%M:%S')} UTC

⚡ <i>Signal envoyé automatiquement par TradingBot</i>
""".strip()


def build_tp_telegram_message(signal) -> str:
    asset = signal.asset.upper()
    action = signal.action.upper()
    asset_icon = asset_emoji(asset)
    dir_icon = action_emoji(action)
    pnl = calculate_trade_pnl(signal)

    return f"""
✅ <b>TAKE PROFIT TOUCHÉ</b>

💎 <b>TradingSignals Premium</b>

{asset_icon} <b>Actif :</b> {asset}
{dir_icon} <b>Direction :</b> {action}

🆔 <b>Trade ID :</b> {signal.trade_id or "-"}
💰 <b>Entrée :</b> {format_price(signal.entry_price)}
🎯 <b>TP atteint :</b> {format_price(signal.take_profit)}
💵 <b>PnL :</b> +{format_price(abs(pnl))}

📌 <b>Statut :</b> 🟢 WIN
🏆 <i>Trade gagnant clôturé</i>
""".strip()


def build_sl_telegram_message(signal) -> str:
    asset = signal.asset.upper()
    action = signal.action.upper()
    asset_icon = asset_emoji(asset)
    dir_icon = action_emoji(action)
    pnl = calculate_trade_pnl(signal)

    return f"""
❌ <b>STOP LOSS TOUCHÉ</b>

💎 <b>TradingSignals Premium</b>

{asset_icon} <b>Actif :</b> {asset}
{dir_icon} <b>Direction :</b> {action}

🆔 <b>Trade ID :</b> {signal.trade_id or "-"}
💰 <b>Entrée :</b> {format_price(signal.entry_price)}
🛑 <b>SL atteint :</b> {format_price(signal.stop_loss)}
💵 <b>PnL :</b> -{format_price(abs(pnl))}

📌 <b>Statut :</b> 🔴 LOSS
⚠️ <i>Trade clôturé en perte</i>
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


from app.services.signal_service import calculate_trade_pnl