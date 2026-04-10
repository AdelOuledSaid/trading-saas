from datetime import datetime, timedelta

from app import create_app
from app.extensions import db
from app.models.signal import Signal
from app.models.replay import TradeReplay, ReplayCandle, ReplayEvent

app = create_app()

with app.app_context():
    # =========================
    # 1. PRENDRE UN SIGNAL EXISTANT
    # =========================
    signal = Signal.query.order_by(Signal.id.asc()).first()

    if not signal:
        print("Aucun signal trouvé dans la base. Crée d'abord un signal.")
        raise SystemExit(1)

    # Vérifie qu'il n'a pas déjà un replay
    existing_replay = TradeReplay.query.filter_by(signal_id=signal.id).first()
    if existing_replay:
        print(f"Un replay existe déjà pour le signal {signal.id}. Replay ID = {existing_replay.id}")
        raise SystemExit(0)

    # =========================
    # 2. DATES DE TEST
    # =========================
    now = datetime.utcnow()
    replay_start = now - timedelta(hours=2)
    entry_time = now - timedelta(hours=1, minutes=15)
    exit_time = now - timedelta(minutes=15)
    replay_end = now

    # =========================
    # 3. CRÉER LE REPLAY
    # =========================
    replay = TradeReplay(
        signal_id=signal.id,
        symbol=signal.asset,
        timeframe=signal.timeframe or "M15",
        direction=signal.action,
        replay_start=replay_start,
        replay_end=replay_end,
        entry_time=entry_time,
        exit_time=exit_time,
        entry_price=signal.entry_price,
        stop_loss=signal.stop_loss,
        take_profit=signal.take_profit,
        result="WIN" if signal.status == "CLOSED" else "OPEN",
        result_percent=signal.result_percent if signal.result_percent is not None else 1.25,
        market_context=signal.reason or "Setup technique détecté avec contexte favorable.",
        post_analysis="Replay de démonstration généré pour le module Velwolf Replay."
    )

    db.session.add(replay)
    db.session.flush()

    # =========================
    # 4. GÉNÉRER DES BOUGIES FACTICES
    # =========================
    base = signal.entry_price

    candles_data = [
        (entry_time - timedelta(minutes=30), base - 40, base - 10, base - 60, base - 20, 1100, 0),
        (entry_time - timedelta(minutes=15), base - 20, base + 10, base - 30, base + 5, 1300, 1),
        (entry_time,                      base + 5,  base + 30, base - 5,  base + 20, 1500, 2),
        (entry_time + timedelta(minutes=15), base + 20, base + 60, base + 10, base + 45, 1700, 3),
        (entry_time + timedelta(minutes=30), base + 45, base + 90, base + 35, base + 80, 1900, 4),
        (entry_time + timedelta(minutes=45), base + 80, base + 130, base + 70, base + 120, 2100, 5),
    ]

    candles = [
        ReplayCandle(
            trade_replay_id=replay.id,
            candle_time=dt,
            open=o,
            high=h,
            low=l,
            close=c,
            volume=v,
            position_index=idx
        )
        for dt, o, h, l, c, v, idx in candles_data
    ]

    db.session.add_all(candles)

    # =========================
    # 5. AJOUTER DES ÉVÉNEMENTS
    # =========================
    events = [
        ReplayEvent(
            trade_replay_id=replay.id,
            event_time=entry_time,
            event_type="entry",
            title="Entrée validée",
            description="Le signal entre en position sur confirmation du setup.",
            price_level=signal.entry_price,
            position_index=2
        ),
        ReplayEvent(
            trade_replay_id=replay.id,
            event_time=entry_time + timedelta(minutes=15),
            event_type="confirmation",
            title="Momentum confirmé",
            description="Le marché évolue dans le sens du trade avec accélération.",
            price_level=base + 45,
            position_index=3
        ),
        ReplayEvent(
            trade_replay_id=replay.id,
            event_time=entry_time + timedelta(minutes=45),
            event_type="tp_hit",
            title="Objectif atteint",
            description="Le prix atteint la zone cible du trade.",
            price_level=signal.take_profit if signal.take_profit else base + 120,
            position_index=5
        )
    ]

    db.session.add_all(events)
    db.session.commit()

    print(f"Replay créé avec succès.")
    print(f"Signal ID : {signal.id}")
    print(f"Replay ID : {replay.id}")
    print(f"URL page : http://127.0.0.1:5000/replay/{replay.id}")
    print(f"URL API  : http://127.0.0.1:5000/api/replay/{replay.id}")