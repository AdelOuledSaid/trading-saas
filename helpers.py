import random
import requests
import stripe

from datetime import datetime, timedelta
from functools import wraps
from flask import current_app, redirect, url_for, flash
from flask_login import current_user

import config
from extensions import db, cache
from models import DailyBriefing, User, Signal
from ai_briefing import generate_daily_briefing
from market_data import get_btc_data, get_gold_data, get_economic_calendar


# =========================
# LOGIN
# =========================
def load_user(user_id):
    return db.session.get(User, int(user_id))


# =========================
# TELEGRAM HELPERS
# =========================
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


# =========================
# PLAN HELPERS
# =========================
def get_price_id_for_plan(plan: str) -> str:
    plan = (plan or "").strip().lower()

    if plan == "basic":
        return config.STRIPE_PRICE_BASIC
    if plan == "premium":
        return config.STRIPE_PRICE_PREMIUM
    if plan == "vip":
        return config.STRIPE_PRICE_VIP

    return ""


def normalize_plan(plan: str) -> str:
    plan = (plan or "").strip().lower()
    if plan in ["basic", "premium", "vip"]:
        return plan
    return "free"


def user_has_plan(user, required_plan: str) -> bool:
    hierarchy = {
        "free": 0,
        "basic": 1,
        "premium": 2,
        "vip": 3,
    }
    current = hierarchy.get((user.plan or "free").lower(), 0)
    needed = hierarchy.get(required_plan.lower(), 0)
    return current >= needed


def plan_required(required_plan):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("login"))

            sync_user_premium_status(current_user)

            if not user_has_plan(current_user, required_plan):
                flash(f"Accès réservé au plan {required_plan.upper()} ou supérieur.")
                return redirect(url_for("pricing"))

            return f(*args, **kwargs)
        return decorated_function
    return decorator


# =========================
# STRIPE HELPERS
# =========================
def get_subscription_status(subscription_id: str):
    if not subscription_id or not config.STRIPE_SECRET_KEY:
        return None

    try:
        subscription = stripe.Subscription.retrieve(subscription_id)
        return subscription.get("status")
    except Exception as e:
        current_app.logger.error("Erreur récupération abonnement Stripe: %s", repr(e))
        return None


def has_active_stripe_subscription(user) -> bool:
    if not user or not user.stripe_subscription_id:
        return False

    status = get_subscription_status(user.stripe_subscription_id)
    return status in ["trialing", "active", "past_due"]


def sync_user_premium_status(user) -> None:
    if not user:
        return

    active = has_active_stripe_subscription(user)

    if active:
        changed = False

        if not user.is_premium:
            user.is_premium = True
            changed = True

        if (user.plan or "free") == "free":
            user.plan = "basic"
            changed = True

        if changed:
            db.session.commit()
            current_app.logger.info("Premium synchronisé à TRUE pour %s", user.email)
    else:
        if user.is_premium and user.stripe_subscription_id:
            user.is_premium = False
            user.plan = "free"
            db.session.commit()
            current_app.logger.info("Premium synchronisé à FALSE pour %s", user.email)


# =========================
# SIGNAL HELPERS
# =========================
def calculate_trade_pnl(signal) -> float:
    trade_pnl = 0.0

    if signal.status == "WIN":
        if signal.action == "BUY" and signal.take_profit is not None:
            trade_pnl = signal.take_profit - signal.entry_price
        elif signal.action == "SELL" and signal.take_profit is not None:
            trade_pnl = signal.entry_price - signal.take_profit

    elif signal.status == "LOSS":
        if signal.action == "BUY" and signal.stop_loss is not None:
            trade_pnl = signal.stop_loss - signal.entry_price
        elif signal.action == "SELL" and signal.stop_loss is not None:
            trade_pnl = signal.entry_price - signal.stop_loss

    return round(trade_pnl, 2)


def get_asset_distances(asset: str, data: dict) -> tuple[float, float]:
    asset = asset.upper()

    if asset == "BTCUSD":
        default_sl, default_tp = 100, 200
    elif asset == "ETHUSD":
        default_sl, default_tp = 40, 80
    elif asset == "SOLUSD":
        default_sl, default_tp = 6, 12
    elif asset == "XRPUSD":
        default_sl, default_tp = 0.02, 0.04
    elif asset == "GOLD":
        default_sl, default_tp = 5, 10
    elif asset == "US100":
        default_sl, default_tp = 80, 160
    elif asset == "US500":
        default_sl, default_tp = 20, 40
    elif asset == "FRA40":
        default_sl, default_tp = 35, 70
    else:
        default_sl, default_tp = 100, 200

    sl_distance = float(data.get("sl_distance", default_sl))
    tp_distance = float(data.get("tp_distance", default_tp))
    return sl_distance, tp_distance


def close_signal_as_result(signal: Signal, result_event: str) -> None:
    signal.status = "WIN" if result_event == "TP" else "LOSS"
    signal.closed_at = datetime.utcnow()
    db.session.commit()


def find_open_signal_for_closure(trade_id: str, asset: str):
    signal = None

    if trade_id:
        signal = Signal.query.filter_by(trade_id=trade_id, status="OPEN").first()

    if not signal and asset:
        signal = (
            Signal.query
            .filter_by(asset=asset, status="OPEN")
            .order_by(Signal.created_at.desc())
            .first()
        )

    return signal


# =========================
# BRIEFING HELPERS
# =========================
def ensure_daily_briefing():
    today = datetime.utcnow().date()
    existing = DailyBriefing.query.filter_by(date=today).first()

    if existing:
        return existing

    try:
        btc_data = get_btc_data()
        gold_data = get_gold_data()
        eco_data = get_economic_calendar()

        content = generate_daily_briefing(btc_data, gold_data, eco_data)

        briefing = DailyBriefing(
            date=today,
            content=content
        )

        db.session.add(briefing)
        db.session.commit()
        current_app.logger.info("Briefing du jour généré automatiquement.")
        return briefing

    except Exception as e:
        current_app.logger.error("Erreur génération briefing: %s", repr(e))
        return None


# =========================
# MARKET UPDATES HELPERS
# =========================
def get_market_updates():
    if not config.NEWS_API_KEY:
        current_app.logger.warning("NEWS_API_KEY manquante. Market Updates vide.")
        return []

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": '(bitcoin OR btc OR ethereum OR eth OR gold OR "nasdaq" OR "us100" OR crypto)',
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 6,
        "apiKey": config.NEWS_API_KEY,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        articles = []
        for article in data.get("articles", []):
            image_url = article.get("urlToImage")
            title = article.get("title")
            source = (article.get("source") or {}).get("name", "Source")
            article_url = article.get("url")
            description = article.get("description") or ""

            if not title or not article_url:
                continue

            articles.append({
                "title": title,
                "description": description,
                "image": image_url,
                "source": source,
                "url": article_url,
            })

        return articles[:6]

    except Exception as e:
        current_app.logger.error("Erreur récupération Market Updates: %s", repr(e))
        return []


# =========================
# CRYPTO LIVE DATA
# =========================
def coingecko_headers():
    headers = {"accept": "application/json"}
    if config.COINGECKO_API_KEY:
        headers["x-cg-pro-api-key"] = config.COINGECKO_API_KEY
    return headers


def format_big_number(value):
    try:
        value = float(value)
    except Exception:
        return "..."

    if value >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:.2f}T"
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value / 1_000:.2f}K"
    return f"{value:.2f}"


@cache.memoize(timeout=120)
def get_crypto_market_live(ids="bitcoin,ethereum"):
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": ids,
        "vs_currencies": "usd",
        "include_market_cap": "true",
        "include_24hr_vol": "true",
        "include_24hr_change": "true",
        "include_last_updated_at": "true",
    }

    try:
        response = requests.get(url, params=params, headers=coingecko_headers(), timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        current_app.logger.error("Erreur crypto live: %s", repr(e))
        return {}


@cache.memoize(timeout=600)
def get_asset_news(asset_key, limit=6):
    if not config.NEWS_API_KEY:
        return []

    queries = {
        "BTC": '(bitcoin OR btc)',
        "ETH": '(ethereum OR eth)',
    }

    q = queries.get(asset_key.upper())
    if not q:
        return []

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": q,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": limit,
        "apiKey": config.NEWS_API_KEY,
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        articles = []
        for a in data.get("articles", []):
            if not a.get("title") or not a.get("url"):
                continue

            articles.append({
                "title": a["title"],
                "description": a.get("description", ""),
                "image": a.get("urlToImage"),
                "source": a.get("source", {}).get("name", "Source"),
                "url": a["url"],
            })

        return articles[:limit]

    except Exception as e:
        current_app.logger.error("Erreur news: %s", repr(e))
        return []


@cache.memoize(timeout=300)
def get_fear_greed_live():
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        data = r.json()["data"][0]
        return {
            "value": data["value"],
            "classification": data["value_classification"]
        }
    except Exception:
        return {"value": "...", "classification": "..."}


@cache.memoize(timeout=300)
def get_btc_dominance_live():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/global", timeout=10)
        data = r.json()["data"]
        return round(data["market_cap_percentage"]["btc"], 2)
    except Exception:
        return "..."


# =========================
# FAKE DATA HELPERS
# =========================
def get_fake_asset_base_price(asset: str) -> float:
    prices = {
        "BTCUSD": 68000,
        "ETHUSD": 3200,
        "SOLUSD": 140,
        "XRPUSD": 0.62,
        "GOLD": 3050,
        "US100": 18200,
        "US500": 5400,
        "FRA40": 8100,
    }
    return prices.get(asset.upper(), 1000)


def generate_fake_signal(asset: str, created_at: datetime, idx: int) -> Signal:
    asset = asset.upper()
    action = random.choice(["BUY", "SELL"])

    base_price = get_fake_asset_base_price(asset)

    if asset == "BTCUSD":
        entry_price = round(base_price + random.uniform(-2500, 2500), 2)
        sl_distance = random.uniform(120, 260)
        tp_distance = random.uniform(180, 420)
    elif asset == "ETHUSD":
        entry_price = round(base_price + random.uniform(-180, 180), 2)
        sl_distance = random.uniform(20, 60)
        tp_distance = random.uniform(30, 90)
    elif asset == "SOLUSD":
        entry_price = round(base_price + random.uniform(-12, 12), 2)
        sl_distance = random.uniform(3, 8)
        tp_distance = random.uniform(5, 14)
    elif asset == "XRPUSD":
        entry_price = round(base_price + random.uniform(-0.08, 0.08), 4)
        sl_distance = random.uniform(0.01, 0.025)
        tp_distance = random.uniform(0.015, 0.04)
    elif asset == "GOLD":
        entry_price = round(base_price + random.uniform(-35, 35), 2)
        sl_distance = random.uniform(4, 10)
        tp_distance = random.uniform(7, 18)
    elif asset == "US100":
        entry_price = round(base_price + random.uniform(-350, 350), 2)
        sl_distance = random.uniform(45, 110)
        tp_distance = random.uniform(70, 190)
    elif asset == "US500":
        entry_price = round(base_price + random.uniform(-90, 90), 2)
        sl_distance = random.uniform(12, 26)
        tp_distance = random.uniform(18, 42)
    elif asset == "FRA40":
        entry_price = round(base_price + random.uniform(-180, 180), 2)
        sl_distance = random.uniform(22, 50)
        tp_distance = random.uniform(35, 85)
    else:
        entry_price = round(base_price + random.uniform(-100, 100), 2)
        sl_distance = random.uniform(10, 20)
        tp_distance = random.uniform(15, 30)

    decimals = 4 if asset == "XRPUSD" else 2

    if action == "BUY":
        stop_loss = round(entry_price - sl_distance, decimals)
        take_profit = round(entry_price + tp_distance, decimals)
    else:
        stop_loss = round(entry_price + sl_distance, decimals)
        take_profit = round(entry_price - tp_distance, decimals)

    r = random.random()
    if r < 0.68:
        status = "WIN"
        closed_at = created_at + timedelta(hours=random.randint(1, 18), minutes=random.randint(5, 55))
    elif r < 0.90:
        status = "LOSS"
        closed_at = created_at + timedelta(hours=random.randint(1, 18), minutes=random.randint(5, 55))
    else:
        status = "OPEN"
        closed_at = None

    return Signal(
        trade_id=f"FAKE_{asset}_{created_at.strftime('%Y%m%d%H%M%S')}_{idx}",
        asset=asset,
        action=action,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        status=status,
        created_at=created_at,
        closed_at=closed_at
    )