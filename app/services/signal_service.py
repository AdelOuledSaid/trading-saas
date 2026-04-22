from datetime import datetime
from app.extensions import db
from app.models import Signal
from app.services.ai_signal_service import compute_confidence, generate_reason


# =========================
# PNL CALCULATION
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


# =========================
# DISTANCES PAR ASSET
# =========================
def get_asset_distances(asset: str, data: dict) -> tuple[float, float]:
    asset = asset.upper()

    defaults = {
        "BTCUSD": (100, 200),
        "ETHUSD": (40, 80),
        "SOLUSD": (6, 12),
        "XRPUSD": (0.02, 0.04),
        "GOLD": (5, 10),
        "US100": (80, 160),
        "US500": (20, 40),
        "FRA40": (35, 70),
    }

    default_sl, default_tp = defaults.get(asset, (100, 200))

    sl_distance = float(data.get("sl_distance", default_sl))
    tp_distance = float(data.get("tp_distance", default_tp))

    return sl_distance, tp_distance


# =========================
# CLOSE SIGNAL (MANUAL / WEBHOOK)
# =========================
def close_signal_as_result(signal: Signal, result_event: str) -> None:
    signal.status = "WIN" if result_event == "TP" else "LOSS"
    signal.closed_at = datetime.utcnow()

    # calcul PnL %
    try:
        entry = signal.entry_price
        price = signal.take_profit if result_event == "TP" else signal.stop_loss

        if signal.action == "BUY":
            pnl = (price - entry) / entry * 100
        else:
            pnl = (entry - price) / entry * 100

        signal.result_percent = round(pnl, 2)
    except Exception:
        pass

    db.session.commit()


# =========================
# FIND SIGNAL
# =========================
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
# CREATE SIGNAL
# =========================
def create_signal(data: dict) -> Signal:
    from app.services.replay_recorder_service import ensure_trade_replay_for_signal
    from flask import current_app

    signal = Signal(
        trade_id=data.get("trade_id"),
        asset=data.get("asset"),
        action=data.get("action"),
        entry_price=data.get("entry_price"),
        stop_loss=data.get("stop_loss"),
        take_profit=data.get("take_profit"),
        timeframe=data.get("timeframe"),
        signal_type=data.get("signal_type", "intraday"),
        market_trend=data.get("trend"),
        status="OPEN"  # 🔥 important
    )

    # =========================
    # IA
    # =========================
    ai_data = {
        "rsi": data.get("rsi"),
        "trend": data.get("trend"),
        "breakout": data.get("breakout"),
        "volume": data.get("volume"),
        "news_sentiment": data.get("news_sentiment")
    }

    signal.confidence = compute_confidence(ai_data)
    signal.reason = generate_reason(ai_data)

    db.session.add(signal)
    db.session.commit()

    # =========================
    # REPLAY AUTO
    # =========================
    try:
        ensure_trade_replay_for_signal(signal)
    except Exception as e:
        current_app.logger.warning(
            "Replay auto non créé pour signal %s: %r", signal.id, e
        )

    return signal


# =========================
# 🔥 AUTO STATUS ENGINE (IMPORTANT)
# =========================
def auto_update_signal_status(price_map: dict):
    """
    price_map = {
        "BTCUSD": 65000,
        "ETHUSD": 3200,
        ...
    }
    """

    signals = Signal.query.filter_by(status="OPEN").all()

    updated = 0

    for s in signals:
        try:
            price = price_map.get(s.asset)

            if not price:
                continue

            entry = s.entry_price
            sl = s.stop_loss
            tp = s.take_profit

            if not entry or not sl or not tp:
                continue

            direction = (s.action or "BUY").upper()

            # =========================
            # LOGIQUE PRO
            # =========================
            if direction == "BUY":
                if price >= tp:
                    close_signal_as_result(s, "TP")
                    updated += 1
                elif price <= sl:
                    close_signal_as_result(s, "SL")
                    updated += 1

            elif direction == "SELL":
                if price <= tp:
                    close_signal_as_result(s, "TP")
                    updated += 1
                elif price >= sl:
                    close_signal_as_result(s, "SL")
                    updated += 1

        except Exception as e:
            print("Auto status error:", e)

    return updated