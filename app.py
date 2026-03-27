import os
from datetime import datetime

import requests
import stripe
from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

# =========================
# CONFIG
# =========================
load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-moi-plus-tard")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
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

    is_premium = db.Column(db.Boolean, default=False)

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
        print("Telegram non configuré.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        print("TELEGRAM STATUS:", response.status_code)
        print("TELEGRAM RESPONSE:", response.text)
    except Exception as e:
        print("Erreur Telegram :", e)


# =========================
# STRIPE HELPERS
# =========================
def has_active_stripe_subscription(user) -> bool:
    if not user:
        print("DEBUG Stripe: user absent")
        return False

    if not user.stripe_subscription_id:
        print(f"DEBUG Stripe: pas de stripe_subscription_id pour {user.email}")
        return False

    if not STRIPE_SECRET_KEY:
        print("DEBUG Stripe: STRIPE_SECRET_KEY manquant")
        return False

    try:
        subscription = stripe.Subscription.retrieve(user.stripe_subscription_id)
        status = subscription["status"]

        print("DEBUG Stripe subscription retrieve OK")
        print("DEBUG email =", user.email)
        print("DEBUG subscription_id =", user.stripe_subscription_id)
        print("DEBUG status =", status)

        return status in ["trialing", "active", "past_due"]

    except Exception as e:
        print("Erreur vérification abonnement Stripe:", repr(e))
        return False


def sync_user_premium_status(user) -> None:
    if not user:
        return

    print(
        f"DEBUG sync avant -> "
        f"email={user.email}, "
        f"is_premium={user.is_premium}, "
        f"customer_id={user.stripe_customer_id}, "
        f"sub_id={user.stripe_subscription_id}"
    )

    active = has_active_stripe_subscription(user)

    print(f"DEBUG sync résultat Stripe -> active={active}")

    if active and not user.is_premium:
        user.is_premium = True
        db.session.commit()
        print(f"✅ Synchronisation premium activée pour {user.email}")

    elif not active and user.is_premium and user.stripe_subscription_id:
        user.is_premium = False
        db.session.commit()
        print(f"⚠️ Synchronisation premium désactivée pour {user.email}")

    else:
        print(f"DEBUG sync: aucun changement pour {user.email}")

# =========================
# PROTECTION PREMIUM
# =========================
def premium_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("login"))

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

        # 🔥 FORCE REFRESH USER
        login_user(current_user)

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

# 👉 AJOUT ICI
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
        # 1) créer un client Stripe une seule fois si absent
        if not current_user.stripe_customer_id:
            customer = stripe.Customer.create(
                email=current_user.email
            )
            current_user.stripe_customer_id = customer["id"]
            db.session.commit()
            print(f"✅ Nouveau client Stripe créé : {current_user.stripe_customer_id}")

        # 2) créer la session Checkout en réutilisant CE client Stripe
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
        print("Erreur Stripe create_checkout_session:", repr(e))
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
        print("Erreur Stripe customer portal:", repr(e))
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
            print("DEBUG success session_id =", session_id)
            print("DEBUG success session_data subscription =", session_data["subscription"] if "subscription" in session_data else None)
            print("DEBUG success session_data customer =", session_data["customer"] if "customer" in session_data else None)
        except Exception as e:
            print("Erreur récupération session Stripe:", repr(e))

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
        print("Webhook secret manquant")
        return "", 500

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        print("Payload invalide")
        return "", 400
    except stripe.error.SignatureVerificationError:
        print("Signature invalide")
        return "", 400

    event_type = event["type"]
    data_object = event["data"]["object"]

    print("Stripe event reçu:", event_type)

    try:
        if event_type == "checkout.session.completed":
            metadata = data_object["metadata"] if "metadata" in data_object else {}
            user_id = metadata["user_id"] if "user_id" in metadata else None

            if not user_id and "client_reference_id" in data_object:
                user_id = data_object["client_reference_id"]

            customer_id = data_object["customer"] if "customer" in data_object else None
            subscription_id = data_object["subscription"] if "subscription" in data_object else None
            customer_email = data_object["customer_email"] if "customer_email" in data_object else None

            print("DEBUG checkout.session.completed")
            print("user_id =", user_id)
            print("customer_email =", customer_email)
            print("customer_id =", customer_id)
            print("subscription_id =", subscription_id)

            user = None

            if user_id:
                try:
                    user = db.session.get(User, int(user_id))
                except Exception as e:
                    print("Erreur conversion user_id:", repr(e))

            if not user and customer_email:
                user = User.query.filter_by(email=customer_email.strip().lower()).first()

            if user:
                user.is_premium = True
                user.stripe_customer_id = customer_id
                user.stripe_subscription_id = subscription_id
                db.session.commit()
                print(f"✅ Premium activé pour {user.email}")

                send_telegram_message(
                    f"✅ Nouvel abonnement Premium\n"
                    f"Utilisateur: {user.email}\n"
                    f"Subscription: {subscription_id}"
                )
            else:
                print("⚠️ Aucun utilisateur trouvé pour checkout.session.completed")

        elif event_type == "customer.subscription.updated":
            customer_id = data_object["customer"] if "customer" in data_object else None
            subscription_id = data_object["id"] if "id" in data_object else None
            status = data_object["status"] if "status" in data_object else None

            print("DEBUG customer.subscription.updated")
            print("customer_id =", customer_id)
            print("subscription_id =", subscription_id)
            print("status =", status)

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
                print(f"✅ Subscription updated: {user.email} -> {status}")
            else:
                print("⚠️ Aucun utilisateur trouvé pour customer.subscription.updated")

        elif event_type == "customer.subscription.deleted":
            customer_id = data_object["customer"] if "customer" in data_object else None
            subscription_id = data_object["id"] if "id" in data_object else None

            print("DEBUG customer.subscription.deleted")
            print("customer_id =", customer_id)
            print("subscription_id =", subscription_id)

            user = None

            if subscription_id:
                user = User.query.filter_by(stripe_subscription_id=subscription_id).first()

            if not user and customer_id:
                user = User.query.filter_by(stripe_customer_id=customer_id).first()

            if user:
                user.is_premium = False
                user.stripe_subscription_id = None
                db.session.commit()
                print(f"✅ Premium désactivé pour {user.email}")

                send_telegram_message(
                    f"⚠️ Abonnement annulé\n"
                    f"Utilisateur: {user.email}\n"
                    f"Subscription: {subscription_id}"
                )
            else:
                print("⚠️ Aucun utilisateur trouvé pour customer.subscription.deleted")

        elif event_type == "invoice.payment_succeeded":
            customer_id = data_object["customer"] if "customer" in data_object else None
            subscription_id = data_object["subscription"] if "subscription" in data_object else None

            print("DEBUG invoice.payment_succeeded")
            print("customer_id =", customer_id)
            print("subscription_id =", subscription_id)

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
                print(f"✅ Paiement réussi pour {user.email}")

        elif event_type == "invoice.payment_failed":
            customer_id = data_object["customer"] if "customer" in data_object else None
            subscription_id = data_object["subscription"] if "subscription" in data_object else None

            print("DEBUG invoice.payment_failed")
            print("customer_id =", customer_id)
            print("subscription_id =", subscription_id)

            user = None

            if subscription_id:
                user = User.query.filter_by(stripe_subscription_id=subscription_id).first()

            if not user and customer_id:
                user = User.query.filter_by(stripe_customer_id=customer_id).first()

            if user:
                user.is_premium = False
                db.session.commit()
                print(f"❌ Paiement échoué pour {user.email}")

                send_telegram_message(
                    f"❌ Paiement Stripe échoué\n"
                    f"Utilisateur: {user.email}"
                )

        else:
            print(f"ℹ️ Événement ignoré: {event_type}")

    except Exception as e:
        print("Erreur traitement webhook Stripe:", repr(e))
        return "", 200

    return "", 200


# =========================
# WEBHOOK TRADINGVIEW
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    if not data:
        return {"error": "JSON manquant"}, 400

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