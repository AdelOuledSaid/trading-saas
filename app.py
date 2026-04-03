import os
import random
import requests
import stripe

from datetime import datetime, timedelta
from functools import wraps
from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from ai_briefing import generate_daily_briefing
from market_data import get_btc_data, get_gold_data, get_economic_calendar
from flask_caching import Cache
cache = Cache(app, config={
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 300  # 5 minutes
})
# =========================
# CONFIG
# =========================
load_dotenv()

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-moi-plus-tard")

database_url = os.getenv("DATABASE_URL", "sqlite:///users.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["SESSION_COOKIE_SECURE"] = True
app.config["REMEMBER_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PREFERRED_URL_SCHEME"] = "https"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_VIP_INVITE_LINK = os.getenv("TELEGRAM_VIP_INVITE_LINK", "")

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_PRICE_BASIC = os.getenv("STRIPE_PRICE_BASIC", "")
STRIPE_PRICE_PREMIUM = os.getenv("STRIPE_PRICE_PREMIUM", "")
STRIPE_PRICE_VIP = os.getenv("STRIPE_PRICE_VIP", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

TRADINGVIEW_WEBHOOK_SECRET = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "")
DOMAIN = os.getenv("DOMAIN", "http://127.0.0.1:5000").rstrip("/")

NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

ALLOWED_ASSETS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "GOLD", "US100", "US500", "FRA40"]
ALLOWED_ACTIONS = ["BUY", "SELL"]
ALLOWED_EVENTS = ["OPEN", "TP", "SL"]

stripe.api_key = STRIPE_SECRET_KEY

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)
# =========================
# CACHE
# =========================
cache = Cache(config={
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 300
})
cache.init_app(app)
# =========================
# MODELS
# =========================
class DailyBriefing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=True, nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)

    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)

    is_premium = db.Column(db.Boolean, default=False, nullable=False)
    plan = db.Column(db.String(20), default="free", nullable=False)

    stripe_customer_id = db.Column(db.String(255), nullable=True)
    stripe_subscription_id = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Signal(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    trade_id = db.Column(db.String(120), unique=True, nullable=True, index=True)

    asset = db.Column(db.String(50), nullable=False)
    action = db.Column(db.String(10), nullable=False)

    entry_price = db.Column(db.Float, nullable=False)
    stop_loss = db.Column(db.Float, nullable=True)
    take_profit = db.Column(db.Float, nullable=True)

    status = db.Column(db.String(20), default="OPEN", nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    closed_at = db.Column(db.DateTime, nullable=True)


# =========================
# LOGIN
# =========================
@login_manager.user_loader
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
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        app.logger.warning("Telegram non configuré.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        app.logger.info("TELEGRAM STATUS: %s", response.status_code)
        app.logger.info("TELEGRAM RESPONSE: %s", response.text)
    except Exception as e:
        app.logger.error("Erreur Telegram : %s", repr(e))


# =========================
# PLAN HELPERS
# =========================
def get_price_id_for_plan(plan: str) -> str:
    plan = (plan or "").strip().lower()

    if plan == "basic":
        return STRIPE_PRICE_BASIC
    if plan == "premium":
        return STRIPE_PRICE_PREMIUM
    if plan == "vip":
        return STRIPE_PRICE_VIP

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
# HELPERS
# =========================
def get_subscription_status(subscription_id: str):
    if not subscription_id or not STRIPE_SECRET_KEY:
        return None

    try:
        subscription = stripe.Subscription.retrieve(subscription_id)
        return subscription.get("status")
    except Exception as e:
        app.logger.error("Erreur récupération abonnement Stripe: %s", repr(e))
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
            app.logger.info("Premium synchronisé à TRUE pour %s", user.email)
    else:
        if user.is_premium and user.stripe_subscription_id:
            user.is_premium = False
            user.plan = "free"
            db.session.commit()
            app.logger.info("Premium synchronisé à FALSE pour %s", user.email)


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
        app.logger.info("Briefing du jour généré automatiquement.")
        return briefing

    except Exception as e:
        app.logger.error("Erreur génération briefing: %s", repr(e))
        return None


# =========================
# MARKET UPDATES HELPERS
# =========================
def get_market_updates():
    if not NEWS_API_KEY:
        app.logger.warning("NEWS_API_KEY manquante. Market Updates vide.")
        return []

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": '(bitcoin OR btc OR ethereum OR eth OR gold OR "nasdaq" OR "us100" OR crypto)',
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 6,
        "apiKey": NEWS_API_KEY,
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
        app.logger.error("Erreur récupération Market Updates: %s", repr(e))
        return []



# =========================
# CRYPTO LIVE DATA (BTC + ETH)
# =========================
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")


def coingecko_headers():
    headers = {"accept": "application/json"}
    if COINGECKO_API_KEY:
        headers["x-cg-pro-api-key"] = COINGECKO_API_KEY
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
        app.logger.error("Erreur crypto live: %s", repr(e))
        return {}
@cache.memoize(timeout=600)
def get_asset_news(asset_key, limit=6):
    if not NEWS_API_KEY:
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
        "apiKey": NEWS_API_KEY,
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
        app.logger.error("Erreur news: %s", repr(e))
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
    except:
        return {"value": "...", "classification": "..."}
@cache.memoize(timeout=300)
def get_btc_dominance_live():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/global", timeout=10)
        data = r.json()["data"]
        return round(data["market_cap_percentage"]["btc"], 2)
    except:
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


# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    market_updates = get_market_updates()
    return render_template("home.html", market_updates=market_updates)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        if not email or not password:
            flash("Merci de remplir tous les champs.")
            return redirect(url_for("register"))

        if User.query.filter_by(email=email).first():
            flash("Cet email existe déjà.")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)
        new_user = User(email=email, password=hashed_password)

        db.session.add(new_user)
        db.session.commit()

        flash("Compte créé avec succès. Connecte-toi.")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            flash("Connexion réussie.")
            return redirect(url_for("dashboard"))

        flash("Email ou mot de passe incorrect.")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Tu es déconnecté.")
    return redirect(url_for("home"))


@app.route("/pricing")
def pricing():
    if current_user.is_authenticated:
        sync_user_premium_status(current_user)

    return render_template(
        "pricing.html",
        stripe_publishable_key=STRIPE_PUBLISHABLE_KEY,
        user_plan=current_user.plan if current_user.is_authenticated else "free"
    )


@app.route("/dashboard")
@login_required
def dashboard():
    sync_user_premium_status(current_user)

    selected_asset = request.args.get("asset", "").strip().upper()
    if selected_asset and selected_asset not in ALLOWED_ASSETS:
        selected_asset = ""

    base_query = Signal.query
    if selected_asset:
        base_query = base_query.filter_by(asset=selected_asset)

    all_signals = base_query.order_by(Signal.created_at.asc()).all()

    available_assets = [
        row[0]
        for row in db.session.query(Signal.asset).distinct().order_by(Signal.asset).all()
    ]

    if current_user.is_premium:
        signals = all_signals
    else:
        signals = all_signals[-5:]

    total_signals = len(all_signals)
    total_buy = len([s for s in all_signals if s.action == "BUY"])
    total_sell = len([s for s in all_signals if s.action == "SELL"])

    total_win = len([s for s in all_signals if s.status == "WIN"])
    total_loss = len([s for s in all_signals if s.status == "LOSS"])
    total_open = len([s for s in all_signals if s.status == "OPEN"])

    closed_trades = total_win + total_loss
    winrate = round((total_win / closed_trades) * 100, 2) if closed_trades > 0 else 0

    last_signal = all_signals[-1] if all_signals else None
    estimated_pnl = round(sum(calculate_trade_pnl(s) for s in all_signals), 2)

    today = datetime.utcnow().date()
    today_signals = [s for s in all_signals if s.created_at.date() == today]
    today_trades = len(today_signals)
    today_wins = sum(1 for s in today_signals if s.status == "WIN")
    today_losses = sum(1 for s in today_signals if s.status == "LOSS")
    today_pnl = round(sum(calculate_trade_pnl(s) for s in today_signals), 2)

    pnl_labels = []
    pnl_values = []
    cumulative_pnl = 0.0

    closed_signals = [s for s in all_signals if s.status in ["WIN", "LOSS"]]
    for idx, s in enumerate(closed_signals, start=1):
        cumulative_pnl += calculate_trade_pnl(s)
        pnl_labels.append(f"Trade {idx}")
        pnl_values.append(round(cumulative_pnl, 2))

    initial_capital = 1000
    capital = initial_capital
    capital_labels = []
    capital_values = []

    for idx, s in enumerate(closed_signals, start=1):
        capital += calculate_trade_pnl(s)
        capital_labels.append(f"Trade {idx}")
        capital_values.append(round(capital, 2))

    current_capital = round(capital, 2)
    capital_return_pct = round(((current_capital - initial_capital) / initial_capital) * 100, 2)

    latest_briefing = None
    if user_has_plan(current_user, "premium"):
        latest_briefing = ensure_daily_briefing()

    return render_template(
        "dashboard.html",
        email=current_user.email,
        signals=sorted(signals, key=lambda s: s.created_at, reverse=True),
        total_signals=total_signals,
        total_buy=total_buy,
        total_sell=total_sell,
        total_win=total_win,
        total_loss=total_loss,
        total_open=total_open,
        winrate=winrate,
        last_signal=last_signal,
        estimated_pnl=estimated_pnl,
        today_trades=today_trades,
        today_wins=today_wins,
        today_losses=today_losses,
        today_pnl=today_pnl,
        pnl_labels=pnl_labels,
        pnl_values=pnl_values,
        initial_capital=initial_capital,
        current_capital=current_capital,
        capital_return_pct=capital_return_pct,
        capital_labels=capital_labels,
        capital_values=capital_values,
        is_premium=current_user.is_premium,
        user_plan=current_user.plan,
        selected_asset=selected_asset,
        available_assets=available_assets,
        latest_briefing=latest_briefing
    )


@app.route("/debug-user")
@login_required
def debug_user():
    return {
        "email": current_user.email,
        "is_premium": current_user.is_premium,
        "plan": current_user.plan,
        "stripe_customer_id": current_user.stripe_customer_id,
        "stripe_subscription_id": current_user.stripe_subscription_id,
    }


@app.route("/premium-data")
@login_required
@plan_required("basic")
def premium_data():
    return "🔥 Données premium secrètes"


@app.route("/briefing")
@login_required
@plan_required("premium")
def briefing_page():
    briefing = ensure_daily_briefing()
    return render_template("briefing.html", briefing=briefing)


@app.route("/mentions-legales")
def mentions_legales():
    return render_template("mentions_legales.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/cgu")
def cgu():
    return render_template("cgu.html")


# =========================
# STRIPE
# =========================
@app.route("/create-checkout-session", methods=["POST"])
@login_required
def create_checkout_session():
    selected_plan = normalize_plan(request.form.get("plan"))
    price_id = get_price_id_for_plan(selected_plan)

    if selected_plan == "free" or not price_id:
        flash("Plan invalide.")
        return redirect(url_for("pricing"))

    if has_active_stripe_subscription(current_user):
        flash("Un abonnement actif existe déjà sur votre compte.")
        return redirect(url_for("pricing"))

    if not STRIPE_SECRET_KEY:
        flash("Stripe n'est pas configuré correctement.")
        return redirect(url_for("pricing"))

    try:
        if not current_user.stripe_customer_id:
            customer = stripe.Customer.create(email=current_user.email)
            current_user.stripe_customer_id = customer["id"]
            db.session.commit()
            app.logger.info("Nouveau client Stripe créé : %s", current_user.stripe_customer_id)

        session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            customer=current_user.stripe_customer_id,
            client_reference_id=str(current_user.id),
            metadata={
                "user_id": str(current_user.id),
                "user_email": current_user.email,
                "plan": selected_plan,
            },
            success_url=f"{DOMAIN}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{DOMAIN}/cancel",
        )

        return redirect(session.url, code=303)

    except Exception as e:
        app.logger.error("Erreur Stripe create_checkout_session: %s", repr(e))
        flash("Impossible de créer la session de paiement.")
        return redirect(url_for("pricing"))


@app.route("/create-customer-portal-session", methods=["POST"])
@login_required
def create_customer_portal_session():
    if not current_user.stripe_customer_id:
        flash("Aucun client Stripe lié à ce compte.")
        return redirect(url_for("pricing"))

    if not STRIPE_SECRET_KEY:
        flash("Stripe n'est pas configuré correctement.")
        return redirect(url_for("pricing"))

    try:
        session = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url=f"{DOMAIN}/pricing"
        )
        return redirect(session.url, code=303)

    except Exception as e:
        app.logger.error("Erreur Stripe customer portal: %s", repr(e))
        flash("Impossible d'ouvrir le portail client.")
        return redirect(url_for("pricing"))


@app.route("/success")
@login_required
def success():
    session_id = request.args.get("session_id")
    session_data = None
    vip_link = None

    if session_id and STRIPE_SECRET_KEY:
        try:
            session_data = stripe.checkout.Session.retrieve(session_id)

            customer_id = session_data.get("customer")
            subscription_id = session_data.get("subscription")
            metadata = session_data.get("metadata", {})
            selected_plan = normalize_plan(metadata.get("plan"))

            if customer_id and not current_user.stripe_customer_id:
                current_user.stripe_customer_id = customer_id

            if subscription_id and not current_user.stripe_subscription_id:
                current_user.stripe_subscription_id = subscription_id

            status = get_subscription_status(subscription_id) if subscription_id else None
            current_user.is_premium = status in ["trialing", "active", "past_due"]

            if current_user.is_premium and selected_plan != "free":
                current_user.plan = selected_plan

            db.session.commit()

        except Exception as e:
            app.logger.error("Erreur récupération session Stripe: %s", repr(e))

    if (current_user.plan or "").lower() == "vip" and TELEGRAM_VIP_INVITE_LINK:
        vip_link = TELEGRAM_VIP_INVITE_LINK

    return render_template("success.html", session_data=session_data, vip_link=vip_link)


@app.route("/cancel")
@login_required
def cancel():
    return render_template("cancel.html")


@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    if not STRIPE_WEBHOOK_SECRET:
        app.logger.error("Webhook secret Stripe manquant")
        return "", 500

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        app.logger.error("Payload Stripe invalide")
        return "", 400
    except stripe.error.SignatureVerificationError:
        app.logger.error("Signature Stripe invalide")
        return "", 400

    event_type = event["type"]
    data_object = event["data"]["object"]
    app.logger.info("Stripe event reçu: %s", event_type)

    try:
        if event_type == "checkout.session.completed":
            metadata = data_object.get("metadata", {})
            user_id = metadata.get("user_id") or data_object.get("client_reference_id")
            customer_id = data_object.get("customer")
            subscription_id = data_object.get("subscription")
            selected_plan = normalize_plan(metadata.get("plan"))

            customer_email = data_object.get("customer_email")
            if not customer_email:
                customer_details = data_object.get("customer_details", {})
                customer_email = customer_details.get("email")

            user = None
            if user_id:
                try:
                    user = db.session.get(User, int(user_id))
                except Exception as e:
                    app.logger.error("Erreur conversion user_id Stripe: %s", repr(e))

            if not user and customer_email:
                user = User.query.filter_by(email=customer_email.strip().lower()).first()

            if user:
                user.stripe_customer_id = customer_id
                user.stripe_subscription_id = subscription_id
                user.plan = selected_plan if selected_plan != "free" else "basic"
                user.is_premium = True
                db.session.commit()

                send_telegram_message(
                    f"""
✅ <b>CHECKOUT STRIPE TERMINÉ</b>

👤 <b>Utilisateur :</b> {user.email}
🧾 <b>Subscription :</b> {subscription_id}
💎 <b>Plan :</b> {user.plan.upper()}
💳 <b>Statut :</b> Premium activé
""".strip()
                )

                if user.plan == "vip":
                    send_telegram_message(
                        f"""
👑 <b>NOUVEAU CLIENT VIP</b>

👤 <b>Utilisateur :</b> {user.email}
🧾 <b>Subscription :</b> {subscription_id}
🔗 <b>Action :</b> envoyer / vérifier l'accès Telegram VIP
""".strip()
                    )

        elif event_type == "customer.subscription.updated":
            customer_id = data_object.get("customer")
            subscription_id = data_object.get("id")
            status = data_object.get("status")

            user = None
            if subscription_id:
                user = User.query.filter_by(stripe_subscription_id=subscription_id).first()
            if not user and customer_id:
                user = User.query.filter_by(stripe_customer_id=customer_id).first()

            if user:
                user.stripe_customer_id = customer_id
                user.stripe_subscription_id = subscription_id
                user.is_premium = status in ["trialing", "active", "past_due"]

                if user.is_premium and user.plan == "free":
                    user.plan = "basic"

                db.session.commit()

        elif event_type == "customer.subscription.deleted":
            customer_id = data_object.get("customer")
            subscription_id = data_object.get("id")

            user = None
            if subscription_id:
                user = User.query.filter_by(stripe_subscription_id=subscription_id).first()
            if not user and customer_id:
                user = User.query.filter_by(stripe_customer_id=customer_id).first()

            if user:
                user.is_premium = False
                user.plan = "free"
                user.stripe_subscription_id = None
                db.session.commit()

                send_telegram_message(
                    f"""
⚠️ <b>ABONNEMENT ANNULÉ</b>

👤 <b>Utilisateur :</b> {user.email}
🧾 <b>Subscription :</b> {subscription_id}
🔒 <b>Plan :</b> FREE
🔒 <b>Premium :</b> désactivé
""".strip()
                )

        elif event_type == "invoice.payment_succeeded":
            customer_id = data_object.get("customer")
            subscription_id = data_object.get("subscription")

            user = None
            if subscription_id:
                user = User.query.filter_by(stripe_subscription_id=subscription_id).first()
            if not user and customer_id:
                user = User.query.filter_by(stripe_customer_id=customer_id).first()

            if user:
                user.is_premium = True
                if user.plan == "free":
                    user.plan = "basic"
                if customer_id:
                    user.stripe_customer_id = customer_id
                if subscription_id:
                    user.stripe_subscription_id = subscription_id
                db.session.commit()

        elif event_type == "invoice.payment_failed":
            customer_id = data_object.get("customer")
            subscription_id = data_object.get("subscription")

            user = None
            if subscription_id:
                user = User.query.filter_by(stripe_subscription_id=subscription_id).first()
            if not user and customer_id:
                user = User.query.filter_by(stripe_customer_id=customer_id).first()

            if user:
                send_telegram_message(
                    f"""
❌ <b>PAIEMENT STRIPE ÉCHOUÉ</b>

👤 <b>Utilisateur :</b> {user.email}
💳 <b>Action recommandée :</b> vérifier la carte bancaire
""".strip()
                )

    except Exception as e:
        app.logger.error("Erreur traitement webhook Stripe: %s", repr(e))
        return "", 200

    return "", 200


# =========================
# WEBHOOK TRADINGVIEW
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():
    raw_body = request.get_data(as_text=True).strip()
    data = request.get_json(silent=True)

    if not data:
        app.logger.info("Webhook TradingView ignoré (non JSON): %s", raw_body)
        return {"status": "ignored", "reason": "non-json payload"}, 200

    app.logger.info("Webhook TradingView reçu: %s", data)

    if TRADINGVIEW_WEBHOOK_SECRET and data.get("secret") != TRADINGVIEW_WEBHOOK_SECRET:
        app.logger.warning("Webhook TradingView refusé: secret invalide")
        return {"error": "Non autorisé"}, 403

    event_type = str(data.get("event", "OPEN")).strip().upper()

    if event_type not in ALLOWED_EVENTS:
        app.logger.warning("Webhook TradingView: event non autorisé -> %s", event_type)
        return {"error": f"Event non autorisé: {event_type}"}, 400

    if event_type == "OPEN":
        try:
            trade_id = str(data.get("trade_id", "")).strip()
            asset = str(data.get("asset", "")).strip().upper()
            action = str(data.get("action", "")).strip().upper()
            entry_price = float(data.get("entry_price"))
        except Exception:
            app.logger.warning("Webhook TradingView OPEN: données invalides")
            return {"error": "Données invalides"}, 400

        if asset not in ALLOWED_ASSETS:
            app.logger.warning("Webhook TradingView OPEN: actif non autorisé -> %s", asset)
            return {"error": f"Actif non autorisé: {asset}"}, 400

        if action not in ALLOWED_ACTIONS:
            app.logger.warning("Webhook TradingView OPEN: action non autorisée -> %s", action)
            return {"error": f"Action non autorisée: {action}"}, 400

        try:
            sl_distance, tp_distance = get_asset_distances(asset, data)
        except Exception:
            app.logger.warning("Webhook TradingView OPEN: distances invalides")
            return {"error": "Distances SL/TP invalides"}, 400

        if action == "BUY":
            stop_loss = entry_price - sl_distance
            take_profit = entry_price + tp_distance
        else:
            stop_loss = entry_price + sl_distance
            take_profit = entry_price - tp_distance

        if trade_id:
            existing_signal = Signal.query.filter_by(trade_id=trade_id).first()
            if existing_signal:
                app.logger.info("Trade déjà existant, ignoré: %s", trade_id)
                return {
                    "status": "ignored",
                    "reason": "trade_id already exists",
                    "trade_id": trade_id
                }, 200

        signal = Signal(
            trade_id=trade_id if trade_id else None,
            asset=asset,
            action=action,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            status="OPEN"
        )

        db.session.add(signal)
        db.session.commit()

        send_telegram_message(build_signal_telegram_message(signal))

        app.logger.info(
            "Signal OPEN enregistré | trade_id=%s asset=%s action=%s entry=%s",
            trade_id, asset, action, entry_price
        )

        return {
            "status": "ok",
            "event": "OPEN",
            "trade_id": signal.trade_id,
            "asset": asset,
            "action": action,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit
        }, 200

    if event_type in ["TP", "SL"]:
        trade_id = str(data.get("trade_id", "")).strip()
        asset = str(data.get("asset", "")).strip().upper()

        signal = find_open_signal_for_closure(trade_id=trade_id, asset=asset)

        if not signal:
            app.logger.warning(
                "Aucun signal OPEN trouvé pour fermeture | trade_id=%s asset=%s",
                trade_id, asset
            )
            return {"error": "Aucun signal OPEN trouvé"}, 404

        close_signal_as_result(signal, event_type)

        if event_type == "TP":
            send_telegram_message(build_tp_telegram_message(signal))
        else:
            send_telegram_message(build_sl_telegram_message(signal))

        app.logger.info(
            "Signal fermé | trade_id=%s asset=%s result=%s",
            signal.trade_id, signal.asset, signal.status
        )

        return {
            "status": "ok",
            "event": event_type,
            "trade_id": signal.trade_id,
            "asset": signal.asset,
            "result": signal.status
        }, 200

    return {"error": "Event inconnu"}, 400


# =========================
# FAKE DATA ROUTES
# =========================
@app.route("/seed-fake-signals")
def seed_fake_signals():
    existing_fake = Signal.query.filter(Signal.trade_id.like("FAKE_%")).count()
    if existing_fake > 0:
        return f"Des fake signals existent déjà ({existing_fake}). Supprime-les d'abord si tu veux regénérer."

    assets = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "GOLD", "US100", "US500", "FRA40"]
    total_to_create = 120
    now = datetime.utcnow()

    fake_signals = []

    for i in range(total_to_create):
        asset = random.choice(assets)
        days_ago = random.randint(0, 44)
        hours_ago = random.randint(0, 23)
        minutes_ago = random.randint(0, 59)

        created_at = now - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)
        signal = generate_fake_signal(asset=asset, created_at=created_at, idx=i + 1)
        fake_signals.append(signal)

    db.session.bulk_save_objects(fake_signals)
    db.session.commit()

    return f"{len(fake_signals)} fake signals ajoutés avec succès."


@app.route("/delete-fake-signals")
def delete_fake_signals():
    fake_signals = Signal.query.filter(Signal.trade_id.like("FAKE_%")).all()

    count = len(fake_signals)
    for signal in fake_signals:
        db.session.delete(signal)

    db.session.commit()
    return f"{count} fake signals supprimés."


# =========================
# TEST ROUTES
# =========================
@app.route("/test-telegram")
def test_telegram():
    test_message = """
🚀 <b>TEST TELEGRAM RÉUSSI</b>

💎 <b>TradingSignals Premium</b>

📊 <b>Actif :</b> BTCUSD
📈 <b>Direction :</b> BUY

💰 <b>Entrée :</b> 66 375.00
🛑 <b>Stop Loss :</b> 66 352.13
🎯 <b>Take Profit :</b> 66 420.73

📌 <b>Statut :</b> 🟡 OPEN
⚡ <i>Connexion Flask → Telegram OK</i>
""".strip()

    send_telegram_message(test_message)
    return "Message Telegram envoyé"


@app.route("/test-tp")
def test_tp():
    class DummySignal:
        trade_id = "TEST_TP_001"
        asset = "BTCUSD"
        action = "BUY"
        entry_price = 66375
        take_profit = 66420.73
        stop_loss = 66352.13
        status = "WIN"

    send_telegram_message(build_tp_telegram_message(DummySignal()))
    return "Message TP envoyé"


@app.route("/test-sl")
def test_sl():
    class DummySignal:
        trade_id = "TEST_SL_001"
        asset = "BTCUSD"
        action = "BUY"
        entry_price = 66375
        take_profit = 66420.73
        stop_loss = 66352.13
        status = "LOSS"

    send_telegram_message(build_sl_telegram_message(DummySignal()))
    return "Message SL envoyé"


# =========================
# NEW PAGES (SITE PRO)
# =========================
@app.route("/signals")
def signals_page():
    return render_template("signals/index.html")


@app.route("/results")
def results():
    all_signals = Signal.query.order_by(Signal.created_at.desc()).limit(50).all()

    total = len(all_signals)
    wins = len([s for s in all_signals if s.status == "WIN"])
    losses = len([s for s in all_signals if s.status == "LOSS"])

    winrate = round((wins / (wins + losses)) * 100, 2) if (wins + losses) > 0 else 0

    pnl = round(sum(calculate_trade_pnl(s) for s in all_signals), 2)

    return render_template(
        "results.html",
        total_signals=total,
        total_win=wins,
        total_loss=losses,
        winrate=winrate,
        estimated_pnl=pnl,
        signals=all_signals[:10]
    )


@app.route("/faq")
def faq_page():
    return render_template("faq.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


@app.route("/search")
def search_page():
    query = request.args.get("q", "")
    return render_template("search.html", query=query)


@app.route("/about")
def about():
    return render_template("about.html")
@app.route("/signals/btc")
def signals_btc():
    btc_signals = (
        Signal.query
        .filter_by(asset="BTCUSD")
        .order_by(Signal.created_at.desc())
        .limit(20)
        .all()
    )

    crypto = get_crypto_market_live()
    btc = crypto.get("bitcoin", {})

    btc_price = format_price(btc.get("usd")) if btc.get("usd") else "..."
    btc_change = round(btc.get("usd_24h_change", 0), 2) if btc.get("usd_24h_change") else "..."
    btc_market_cap = format_big_number(btc.get("usd_market_cap"))
    btc_volume = format_big_number(btc.get("usd_24h_vol"))

    return render_template(
        "signals/btc.html",
        btc_signals=btc_signals,
        btc_price=btc_price,
        btc_change_24h=btc_change,
        btc_market_cap=btc_market_cap,
        btc_volume_24h=btc_volume,
        btc_news=get_asset_news("BTC"),
        btc_dominance=get_btc_dominance_live(),
        fear_greed=get_fear_greed_live()
    )


@app.route("/signals/eth")
def signals_eth():
    eth_signals = (
        Signal.query
        .filter_by(asset="ETHUSD")
        .order_by(Signal.created_at.desc())
        .limit(20)
        .all()
    )

    crypto = get_crypto_market_live()
    eth = crypto.get("ethereum", {})

    eth_price = format_price(eth.get("usd")) if eth.get("usd") else "..."
    eth_change = round(eth.get("usd_24h_change", 0), 2) if eth.get("usd_24h_change") else "..."
    eth_market_cap = format_big_number(eth.get("usd_market_cap"))
    eth_volume = format_big_number(eth.get("usd_24h_vol"))

    return render_template(
        "signals/eth.html",
        eth_signals=eth_signals,
        eth_price=eth_price,
        eth_change_24h=eth_change,
        eth_market_cap=eth_market_cap,
        eth_volume_24h=eth_volume,
        eth_news=get_asset_news("ETH"),
        fear_greed=get_fear_greed_live()
    )  



@app.route("/signals/gold")
def signals_gold():
    gold_signals = (
        Signal.query
        .filter_by(asset="GOLD")
        .order_by(Signal.created_at.desc())
        .limit(20)
        .all()
    )

    gold_total_signals = Signal.query.filter_by(asset="GOLD").count()
    gold_open_signals = Signal.query.filter_by(asset="GOLD", status="OPEN").count()
    gold_win_signals = Signal.query.filter_by(asset="GOLD", status="WIN").count()
    gold_loss_signals = Signal.query.filter_by(asset="GOLD", status="LOSS").count()

    closed_count = gold_win_signals + gold_loss_signals
    gold_winrate = round((gold_win_signals / closed_count) * 100, 2) if closed_count > 0 else 0

    all_gold_signals = Signal.query.filter_by(asset="GOLD").all()
    gold_estimated_pnl = round(sum(calculate_trade_pnl(s) for s in all_gold_signals), 2)

    return render_template(
        "signals/gold.html",
        gold_signals=gold_signals,
        gold_total_signals=gold_total_signals,
        gold_open_signals=gold_open_signals,
        gold_winrate=gold_winrate,
        gold_estimated_pnl=gold_estimated_pnl
    )


@app.route("/signals/us100")
def signals_us100():
    us100_signals = (
        Signal.query
        .filter_by(asset="US100")
        .order_by(Signal.created_at.desc())
        .limit(20)
        .all()
    )

    us100_total_signals = Signal.query.filter_by(asset="US100").count()
    us100_open_signals = Signal.query.filter_by(asset="US100", status="OPEN").count()
    us100_win_signals = Signal.query.filter_by(asset="US100", status="WIN").count()
    us100_loss_signals = Signal.query.filter_by(asset="US100", status="LOSS").count()

    closed_count = us100_win_signals + us100_loss_signals
    us100_winrate = round((us100_win_signals / closed_count) * 100, 2) if closed_count > 0 else 0

    all_us100_signals = Signal.query.filter_by(asset="US100").all()
    us100_estimated_pnl = round(sum(calculate_trade_pnl(s) for s in all_us100_signals), 2)

    return render_template(
        "signals/us100.html",
        us100_signals=us100_signals,
        us100_total_signals=us100_total_signals,
        us100_open_signals=us100_open_signals,
        us100_winrate=us100_winrate,
        us100_estimated_pnl=us100_estimated_pnl
    )


@app.route("/trading-lab")
def trading_lab():
    return render_template("trading_lab/index.html")


@app.route("/trading-lab/structure")
def lab_structure():
    return render_template("trading_lab/structure.html")


@app.route("/trading-lab/risk")
def lab_risk():
    return render_template("trading_lab/risk.html")


@app.route("/trading-lab/psychology")
def lab_psychology():
    return render_template("trading_lab/psychology.html")


# =========================
# INIT DB
# =========================
with app.app_context():
    db.create_all()


# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(debug=True)