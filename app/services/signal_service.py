from datetime import datetime
from app.extensions import db
from app.models import Signal
from app.services.ai_signal_service import compute_confidence, generate_reason

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

def create_signal(data: dict) -> Signal:
    from app.services.ai_signal_service import compute_confidence, generate_reason

    signal = Signal(
        trade_id=data.get("trade_id"),
        asset=data.get("asset"),
        action=data.get("action"),
        entry_price=data.get("entry_price"),
        stop_loss=data.get("stop_loss"),
        take_profit=data.get("take_profit"),
        timeframe=data.get("timeframe"),
        signal_type=data.get("signal_type", "intraday"),
        market_trend=data.get("trend")
    )

    # 🔥 IA Velwolef
    ai_data = {
        "rsi": data.get("rsi"),
        "trend": data.get("trend"),
        "breakout": data.get("breakout"),
        "volume": data.get("volume"),
        "news_sentiment": data.get("news_sentiment")
    }

    signal.confidence = compute_confidence(ai_data)
    signal.reason = generate_reason(ai_data)

    # save
    db.session.add(signal)
    db.session.commit()

    return signal