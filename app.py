import os
from datetime import datetime
from functools import wraps

import requests
import stripe
from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os

print("OPENAI KEY FOUND:", bool(os.getenv("OPENAI_API_KEY")))
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

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

TRADINGVIEW_WEBHOOK_SECRET = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "")
DOMAIN = os.getenv("DOMAIN", "http://127.0.0.1:5000").rstrip("/")

ALLOWED_ASSETS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "GOLD", "US100", "US500", "FRA40"]
ALLOWED_ACTIONS = ["BUY", "SELL"]
ALLOWED_EVENTS = ["OPEN", "TP", "SL"]

stripe.api_key = STRIPE_SECRET_KEY

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

# =========================
# MODELS
# =========================
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)

    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)

    is_premium = db.Column(db.Boolean, default=False, nullable=False)

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

    status = db.Column(db.String(20), default="OPEN", nullable=False)  # OPEN / WIN / LOSS

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

    if active and not user.is_premium:
        user.is_premium = True
        db.session.commit()
        app.logger.info("Premium synchronisé à TRUE pour %s", user.email)

    elif not active and user.is_premium and user.stripe_subscription_id:
        user.is_premium = False
        db.session.commit()
        app.logger.info("Premium synchronisé à FALSE pour %s", user.email)


def premium_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("login"))

        sync_user_premium_status(current_user)

        if not current_user.is_premium:
            flash("Accès réservé aux utilisateurs Premium.")
            return redirect(url_for("pricing"))

        return f(*args, **kwargs)

    return decorated_function


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


def find_open_signal_for_closure(trade_id: str, asset: str) -> Signal | None:
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
# ROUTES
# =========================
@app.route("/")
def home():
    return render_template("home.html")


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
        stripe_publishable_key=STRIPE_PUBLISHABLE_KEY
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
        selected_asset=selected_asset,
        available_assets=available_assets
    )


@app.route("/debug-user")
@login_required
def debug_user():
    return {
        "email": current_user.email,
        "is_premium": current_user.is_premium,
        "stripe_customer_id": current_user.stripe_customer_id,
        "stripe_subscription_id": current_user.stripe_subscription_id,
    }


@app.route("/premium-data")
@login_required
@premium_required
def premium_data():
    return "🔥 Données premium secrètes"


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
    if current_user.is_premium:
        flash("Votre compte est déjà Premium.")
        return redirect(url_for("pricing"))

    if has_active_stripe_subscription(current_user):
        current_user.is_premium = True
        db.session.commit()
        flash("Un abonnement actif existe déjà sur votre compte.")
        return redirect(url_for("pricing"))

    if not STRIPE_SECRET_KEY or not STRIPE_PRICE_ID:
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
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            customer=current_user.stripe_customer_id,
            client_reference_id=str(current_user.id),
            metadata={
                "user_id": str(current_user.id),
                "user_email": current_user.email,
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

    if session_id and STRIPE_SECRET_KEY:
        try:
            session_data = stripe.checkout.Session.retrieve(session_id)

            customer_id = session_data.get("customer")
            subscription_id = session_data.get("subscription")

            if customer_id and not current_user.stripe_customer_id:
                current_user.stripe_customer_id = customer_id

            if subscription_id and not current_user.stripe_subscription_id:
                current_user.stripe_subscription_id = subscription_id

            status = get_subscription_status(subscription_id) if subscription_id else None
            current_user.is_premium = status in ["trialing", "active", "past_due"]

            db.session.commit()

        except Exception as e:
            app.logger.error("Erreur récupération session Stripe: %s", repr(e))

    return render_template("success.html", session_data=session_data)


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
                db.session.commit()

                send_telegram_message(
                    f"""
✅ <b>CHECKOUT STRIPE TERMINÉ</b>

👤 <b>Utilisateur :</b> {user.email}
🧾 <b>Subscription :</b> {subscription_id}
💳 <b>Statut :</b> En attente de synchronisation
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
                user.stripe_subscription_id = None
                db.session.commit()

                send_telegram_message(
                    f"""
⚠️ <b>ABONNEMENT ANNULÉ</b>

👤 <b>Utilisateur :</b> {user.email}
🧾 <b>Subscription :</b> {subscription_id}
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

    # Ignore les requêtes texte / vides envoyées par erreur
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

    # =========================
    # OPEN
    # =========================
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

        # Évite doublon si même trade_id déjà reçu
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

    # =========================
    # TP / SL
    # =========================
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
# RUN
# =========================
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)