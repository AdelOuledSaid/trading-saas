import random
from datetime import datetime, timedelta
from flask import Blueprint

from app.extensions import db
from app.models import Signal
from app.services.fake_data_service import generate_fake_signal
from app.services.telegram_service import (
    send_telegram_message,
    build_tp_telegram_message,
    build_sl_telegram_message,
)

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/seed-fake-signals")
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


@admin_bp.route("/delete-fake-signals")
def delete_fake_signals():
    fake_signals = Signal.query.filter(Signal.trade_id.like("FAKE_%")).all()

    count = len(fake_signals)
    for signal in fake_signals:
        db.session.delete(signal)

    db.session.commit()
    return f"{count} fake signals supprimés."


@admin_bp.route("/test-telegram")
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


@admin_bp.route("/test-tp")
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


@admin_bp.route("/test-sl")
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