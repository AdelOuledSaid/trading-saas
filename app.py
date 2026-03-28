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

# =========================
# CONFIG
# =========================
load_dotenv()

app = Flask(__name__)

# ---- Core config
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-moi-plus-tard")

database_url = os.getenv("DATABASE_URL", "sqlite:///users.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# ---- Security / cookies
app.config["SESSION_COOKIE_SECURE"] = True
app.config["REMEMBER_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PREFERRED_URL_SCHEME"] = "https"

# ---- External services
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

TRADINGVIEW_WEBHOOK_SECRET = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "")
DOMAIN = os.getenv("DOMAIN", "http://127.0.0.1:5000").rstrip("/")

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
    asset = db.Column(db.String(50), nullable=False)
    action = db.Column(db.String(10), nullable=False)
    entry_price = db.Column(db.Float, nullable=False)
    stop_loss = db.Column(db.Float)
    take_profit = db.Column(db.Float)
    status = db.Column(db.String(20), default="OPEN")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# =========================
# LOGIN
# =========================
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# =========================
# TELEGRAM
# =========================
def send_telegram_message(message: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        app.logger.warning("Telegram non configuré.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        app.logger.info("TELEGRAM STATUS: %s", response.status_code)
        app.logger.info("TELEGRAM RESPONSE: %s", response.text)
    except Exception as e:
        app.logger.error("Erreur Telegram : %s", repr(e))

# =========================
# STRIPE HELPERS
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
    if not user:
        app.logger.warning("DEBUG Stripe: user absent")
        return False

    if not user.stripe_subscription_id:
        app.logger.info("DEBUG Stripe: pas de stripe_subscription_id pour %s", user.email)
        return False

    status = get_subscription_status(user.stripe_subscription_id)
    app.logger.info("DEBUG Stripe status pour %s = %s", user.email, status)

    return status in ["trialing", "active", "past_due"]


def sync_user_premium_status(user) -> None:
    if not user:
        return

    app.logger.info(
        "DEBUG sync avant -> email=%s, is_premium=%s, customer_id=%s, sub_id=%s",
        user.email,
        user.is_premium,
        user.stripe_customer_id,
        user.stripe_subscription_id
    )

    active = has_active_stripe_subscription(user)

    if active and not user.is_premium:
        user.is_premium = True
        db.session.commit()
        app.logger.info("Premium synchronisé à TRUE pour %s", user.email)

    elif not active and user.is_premium and user.stripe_subscription_id:
        user.is_premium = False
        db.session.commit()
        app.logger.info("Premium synchronisé à FALSE pour %s", user.email)

# =========================
# PROTECTION PREMIUM
# =========================
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

    all_signals = Signal.query.order_by(Signal.created_at.asc()).all()

    if current_user.is_premium:
        signals = all_signals
    else:
        signals = all_signals[-5:]

    total_signals = len(all_signals)
    total_buy = Signal.query.filter_by(action="BUY").count()
    total_sell = Signal.query.filter_by(action="SELL").count()

    total_win = Signal.query.filter_by(status="WIN").count()
    total_loss = Signal.query.filter_by(status="LOSS").count()
    total_open = Signal.query.filter_by(status="OPEN").count()

    closed_trades = total_win + total_loss
    winrate = round((total_win / closed_trades) * 100, 2) if closed_trades > 0 else 0

    last_signal = all_signals[-1] if all_signals else None

    estimated_pnl = 0
    for s in all_signals:
        if s.status == "WIN":
            if s.action == "BUY" and s.take_profit is not None:
                estimated_pnl += (s.take_profit - s.entry_price)
            elif s.action == "SELL" and s.take_profit is not None:
                estimated_pnl += (s.entry_price - s.take_profit)
        elif s.status == "LOSS":
            if s.action == "BUY" and s.stop_loss is not None:
                estimated_pnl += (s.stop_loss - s.entry_price)
            elif s.action == "SELL" and s.stop_loss is not None:
                estimated_pnl += (s.entry_price - s.stop_loss)

    estimated_pnl = round(estimated_pnl, 2)

    today = datetime.utcnow().date()
    today_signals = [s for s in all_signals if s.created_at.date() == today]
    today_trades = len(today_signals)
    today_wins = sum(1 for s in today_signals if s.status == "WIN")
    today_losses = sum(1 for s in today_signals if s.status == "LOSS")

    today_pnl = 0
    for s in today_signals:
        if s.status == "WIN":
            if s.action == "BUY" and s.take_profit is not None:
                today_pnl += (s.take_profit - s.entry_price)
            elif s.action == "SELL" and s.take_profit is not None:
                today_pnl += (s.entry_price - s.take_profit)
        elif s.status == "LOSS":
            if s.action == "BUY" and s.stop_loss is not None:
                today_pnl += (s.stop_loss - s.entry_price)
            elif s.action == "SELL" and s.stop_loss is not None:
                today_pnl += (s.entry_price - s.stop_loss)

    today_pnl = round(today_pnl, 2)

    pnl_labels = []
    pnl_values = []
    cumulative_pnl = 0

    closed_signals = [s for s in all_signals if s.status in ["WIN", "LOSS"]]

    for idx, s in enumerate(closed_signals, start=1):
        trade_pnl = 0

        if s.status == "WIN":
            if s.action == "BUY" and s.take_profit is not None:
                trade_pnl = s.take_profit - s.entry_price
            elif s.action == "SELL" and s.take_profit is not None:
                trade_pnl = s.entry_price - s.take_profit
        elif s.status == "LOSS":
            if s.action == "BUY" and s.stop_loss is not None:
                trade_pnl = s.stop_loss - s.entry_price
            elif s.action == "SELL" and s.stop_loss is not None:
                trade_pnl = s.entry_price - s.stop_loss

        cumulative_pnl += trade_pnl
        pnl_labels.append(f"Trade {idx}")
        pnl_values.append(round(cumulative_pnl, 2))

    initial_capital = 1000
    capital = initial_capital
    capital_labels = []
    capital_values = []

    for idx, s in enumerate(closed_signals, start=1):
        trade_pnl = 0

        if s.status == "WIN":
            if s.action == "BUY" and s.take_profit is not None:
                trade_pnl = s.take_profit - s.entry_price
            elif s.action == "SELL" and s.take_profit is not None:
                trade_pnl = s.entry_price - s.take_profit
        elif s.status == "LOSS":
            if s.action == "BUY" and s.stop_loss is not None:
                trade_pnl = s.stop_loss - s.entry_price
            elif s.action == "SELL" and s.stop_loss is not None:
                trade_pnl = s.entry_price - s.stop_loss

        capital += trade_pnl
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
        is_premium=current_user.is_premium
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
            line_items=[
                {
                    "price": STRIPE_PRICE_ID,
                    "quantity": 1,
                }
            ],
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

            app.logger.info("SUCCESS Stripe session_id=%s", session_id)
            app.logger.info("SUCCESS customer_id=%s", customer_id)
            app.logger.info("SUCCESS subscription_id=%s", subscription_id)
            app.logger.info("SUCCESS status=%s", status)

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

                app.logger.info("Checkout terminé pour %s", user.email)

                send_telegram_message(
                    f"✅ Checkout Stripe terminé\n"
                    f"Utilisateur: {user.email}\n"
                    f"Subscription: {subscription_id}"
                )
            else:
                app.logger.warning("Aucun utilisateur trouvé pour checkout.session.completed")

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
                app.logger.info("Subscription updated: %s -> %s", user.email, status)
            else:
                app.logger.warning("Aucun utilisateur trouvé pour customer.subscription.updated")

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

                app.logger.info("Premium désactivé pour %s", user.email)

                send_telegram_message(
                    f"⚠️ Abonnement annulé\n"
                    f"Utilisateur: {user.email}\n"
                    f"Subscription: {subscription_id}"
                )
            else:
                app.logger.warning("Aucun utilisateur trouvé pour customer.subscription.deleted")

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

                app.logger.info("Paiement réussi pour %s", user.email)
            else:
                app.logger.warning("Aucun utilisateur trouvé pour invoice.payment_succeeded")

        elif event_type == "invoice.payment_failed":
            customer_id = data_object.get("customer")
            subscription_id = data_object.get("subscription")

            user = None

            if subscription_id:
                user = User.query.filter_by(stripe_subscription_id=subscription_id).first()

            if not user and customer_id:
                user = User.query.filter_by(stripe_customer_id=customer_id).first()

            if user:
                app.logger.warning("Paiement échoué pour %s", user.email)

                send_telegram_message(
                    f"❌ Paiement Stripe échoué\n"
                    f"Utilisateur: {user.email}"
                )
            else:
                app.logger.warning("Aucun utilisateur trouvé pour invoice.payment_failed")

        else:
            app.logger.info("Événement Stripe ignoré: %s", event_type)

    except Exception as e:
        app.logger.error("Erreur traitement webhook Stripe: %s", repr(e))
        return "", 200

    return "", 200

# =========================
# WEBHOOK TRADINGVIEW
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True)

    if not data:
        return {"error": "JSON manquant"}, 400

    if TRADINGVIEW_WEBHOOK_SECRET and data.get("secret") != TRADINGVIEW_WEBHOOK_SECRET:
        return {"error": "Non autorisé"}, 403

    try:
        asset = data.get("asset")
        action = data.get("action")
        entry_price = float(data.get("entry_price"))
    except Exception:
        return {"error": "Données invalides"}, 400

    if not asset or action not in ["BUY", "SELL"]:
        return {"error": "Paramètres invalides"}, 400

    if action == "BUY":
        stop_loss = entry_price - 100
        take_profit = entry_price + 200
    else:
        stop_loss = entry_price + 100
        take_profit = entry_price - 200

    signal = Signal(
        asset=asset,
        action=action,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        status="OPEN"
    )

    db.session.add(signal)
    db.session.commit()

    message = (
        f"🚨 Nouveau signal\n"
        f"Actif: {asset}\n"
        f"Action: {action}\n"
        f"Prix: {entry_price}\n"
        f"SL: {stop_loss}\n"
        f"TP: {take_profit}\n"
        f"Status: OPEN"
    )
    send_telegram_message(message)

    return {"status": "ok"}


@app.route("/test-telegram")
def test_telegram():
    send_telegram_message("✅ Test Telegram depuis Flask")
    return "Message Telegram envoyé"

# =========================
# RUN
# =========================
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)