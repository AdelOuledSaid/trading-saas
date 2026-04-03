import requests
import stripe

from datetime import datetime, timedelta
from flask import Flask, render_template, redirect, url_for, request, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required, current_user

import config
from extensions import db, login_manager, cache
from models import User, Signal, DailyBriefing
from helpers import (
    load_user,
    send_telegram_message,
    build_signal_telegram_message,
    build_tp_telegram_message,
    build_sl_telegram_message,
    normalize_plan,
    get_price_id_for_plan,
    user_has_plan,
    plan_required,
    sync_user_premium_status,
    has_active_stripe_subscription,
    get_subscription_status,
    calculate_trade_pnl,
    get_asset_distances,
    close_signal_as_result,
    find_open_signal_for_closure,
    ensure_daily_briefing,
    get_market_updates,
    get_crypto_market_live,
    format_big_number,
    get_asset_news,
    get_fear_greed_live,
    get_btc_dominance_live,
    generate_fake_signal,
)

# =========================
# APP
# =========================
app = Flask(__name__)
app.config["SECRET_KEY"] = config.SECRET_KEY
app.config["SQLALCHEMY_DATABASE_URI"] = config.DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["SESSION_COOKIE_SECURE"] = True
app.config["REMEMBER_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PREFERRED_URL_SCHEME"] = "https"

db.init_app(app)
login_manager.init_app(app)
cache.init_app(app)

stripe.api_key = config.STRIPE_SECRET_KEY
login_manager.user_loader(load_user)


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
        stripe_publishable_key=config.STRIPE_PUBLISHABLE_KEY,
        user_plan=current_user.plan if current_user.is_authenticated else "free"
    )


@app.route("/dashboard")
@login_required
def dashboard():
    sync_user_premium_status(current_user)

    selected_asset = request.args.get("asset", "").strip().upper()
    if selected_asset and selected_asset not in config.ALLOWED_ASSETS:
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

    if not config.STRIPE_SECRET_KEY:
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
            success_url=f"{config.DOMAIN}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{config.DOMAIN}/cancel",
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

    if not config.STRIPE_SECRET_KEY:
        flash("Stripe n'est pas configuré correctement.")
        return redirect(url_for("pricing"))

    try:
        session = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url=f"{config.DOMAIN}/pricing"
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

    if session_id and config.STRIPE_SECRET_KEY:
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

    if (current_user.plan or "").lower() == "vip" and config.TELEGRAM_VIP_INVITE_LINK:
        vip_link = config.TELEGRAM_VIP_INVITE_LINK

    return render_template("success.html", session_data=session_data, vip_link=vip_link)


@app.route("/cancel")
@login_required
def cancel():
    return render_template("cancel.html")


@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    if not config.STRIPE_WEBHOOK_SECRET:
        app.logger.error("Webhook secret Stripe manquant")
        return "", 500

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=config.STRIPE_WEBHOOK_SECRET
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

    if config.TRADINGVIEW_WEBHOOK_SECRET and data.get("secret") != config.TRADINGVIEW_WEBHOOK_SECRET:
        app.logger.warning("Webhook TradingView refusé: secret invalide")
        return {"error": "Non autorisé"}, 403

    event_type = str(data.get("event", "OPEN")).strip().upper()

    if event_type not in config.ALLOWED_EVENTS:
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

        if asset not in config.ALLOWED_ASSETS:
            app.logger.warning("Webhook TradingView OPEN: actif non autorisé -> %s", asset)
            return {"error": f"Actif non autorisé: {asset}"}, 400

        if action not in config.ALLOWED_ACTIONS:
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
        import random
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
# NEW PAGES
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

    btc_price = format_big_number(btc.get("usd")) if btc.get("usd") else "..."
    if btc.get("usd"):
        btc_price = f"{btc.get('usd'):,.2f}".replace(",", " ")
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
def eth_signals_page():
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": "ethereum",
            "vs_currencies": "usd",
            "include_market_cap": "true",
            "include_24hr_vol": "true",
            "include_24hr_change": "true"
        }

        res = requests.get(url, params=params, timeout=10)
        data = res.json().get("ethereum", {})

        eth_price = round(data.get("usd", 0), 2)
        eth_change_24h = round(data.get("usd_24h_change", 0), 2)
        eth_volume_24h = round(data.get("usd_24h_vol", 0) / 1e9, 2)
        eth_market_cap = round(data.get("usd_market_cap", 0) / 1e9, 2)

    except Exception:
        eth_price = eth_change_24h = eth_volume_24h = eth_market_cap = None

    try:
        url = "https://api.coingecko.com/api/v3/coins/ethereum"
        res = requests.get(url, timeout=10)
        market = res.json().get("market_data", {})

        eth_high_24h = round(market["high_24h"]["usd"], 2)
        eth_low_24h = round(market["low_24h"]["usd"], 2)

    except Exception:
        eth_high_24h = eth_low_24h = None

    if eth_change_24h:
        if eth_change_24h > 2:
            eth_trend_label = "Haussier 📈"
        elif eth_change_24h < -2:
            eth_trend_label = "Baissier 📉"
        else:
            eth_trend_label = "Neutre"
    else:
        eth_trend_label = "Neutre"

    if eth_change_24h:
        if abs(eth_change_24h) > 4:
            eth_volatility_label = "Élevée ⚡"
        elif abs(eth_change_24h) > 2:
            eth_volatility_label = "Modérée"
        else:
            eth_volatility_label = "Faible"
    else:
        eth_volatility_label = "Modérée"

    try:
        eth_support_1 = round(eth_price * 0.97, 2)
        eth_support_2 = round(eth_price * 0.94, 2)

        eth_resistance_1 = round(eth_price * 1.03, 2)
        eth_resistance_2 = round(eth_price * 1.06, 2)
    except Exception:
        eth_support_1 = eth_support_2 = eth_resistance_1 = eth_resistance_2 = None

    try:
        fg = requests.get("https://api.alternative.me/fng/", timeout=10).json()
        fg_data = fg["data"][0]

        fear_greed_value = fg_data["value"]
        fear_greed_classification = fg_data["value_classification"]

    except Exception:
        fear_greed_value = None
        fear_greed_classification = None

    eth_news = get_asset_news("ETH")

    eth_signals = Signal.query.filter_by(asset="ETHUSD").order_by(Signal.created_at.desc()).limit(10).all()

    total = len(eth_signals)
    wins = len([s for s in eth_signals if s.status == "WIN"])

    eth_total_signals = total
    eth_open_signals = len([s for s in eth_signals if s.status == "OPEN"])

    eth_winrate = round((wins / total) * 100, 2) if total > 0 else 0
    eth_estimated_pnl = wins * 2 - (total - wins)

    return render_template(
        "signals/eth.html",
        eth_price=eth_price,
        eth_change_24h=eth_change_24h,
        eth_volume_24h=eth_volume_24h,
        eth_market_cap=eth_market_cap,
        eth_high_24h=eth_high_24h,
        eth_low_24h=eth_low_24h,
        eth_trend_label=eth_trend_label,
        eth_volatility_label=eth_volatility_label,
        eth_support_1=eth_support_1,
        eth_support_2=eth_support_2,
        eth_resistance_1=eth_resistance_1,
        eth_resistance_2=eth_resistance_2,
        fear_greed_value=fear_greed_value,
        fear_greed_classification=fear_greed_classification,
        eth_news=eth_news,
        eth_signals=eth_signals,
        eth_total_signals=eth_total_signals,
        eth_open_signals=eth_open_signals,
        eth_winrate=eth_winrate,
        eth_estimated_pnl=eth_estimated_pnl
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