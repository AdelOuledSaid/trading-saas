from datetime import datetime, timedelta
from typing import Optional

from app.extensions import db
from app.models import Signal, TradeReplay, ReplayCandle, ReplayEvent
from app.services.binance_market_service import (
    fetch_klines,
    map_signal_asset_to_binance_symbol,
    map_timeframe_to_binance_interval,
    dt_to_ms,
)
from app.services.twelvedata_market_service import (
    fetch_time_series,
    map_signal_asset_to_twelvedata_symbol,
    map_timeframe_to_twelvedata_interval,
)


def build_default_replay_window(signal: Signal) -> tuple[datetime, datetime]:
    created_at = signal.created_at or datetime.utcnow()
    timeframe = str(signal.timeframe or "15m").lower()

    if timeframe in {"1", "1m"}:
        before = timedelta(minutes=20)
        after = timedelta(minutes=60)
    elif timeframe in {"5", "5m"}:
        before = timedelta(minutes=60)
        after = timedelta(hours=3)
    elif timeframe in {"15", "15m"}:
        before = timedelta(hours=2)
        after = timedelta(hours=8)
    elif timeframe in {"30", "30m"}:
        before = timedelta(hours=4)
        after = timedelta(hours=12)
    elif timeframe in {"60", "1h"}:
        before = timedelta(hours=8)
        after = timedelta(hours=24)
    elif timeframe in {"4h"}:
        before = timedelta(days=2)
        after = timedelta(days=4)
    elif timeframe in {"1d"}:
        before = timedelta(days=10)
        after = timedelta(days=15)
    else:
        before = timedelta(hours=2)
        after = timedelta(hours=8)

    return created_at - before, created_at + after


def ensure_trade_replay_for_signal(signal: Signal) -> Optional[TradeReplay]:
    if not signal:
        return None

    existing = signal.replay
    if existing and existing.candles:
        return existing

    replay_start, replay_end = build_default_replay_window(signal)
    asset = (signal.asset or "").upper()

    candles_data = []
    provider_symbol = None
    provider_interval = None

    # 1) Crypto via Binance
    binance_symbol = map_signal_asset_to_binance_symbol(asset)
    if binance_symbol:
        provider_symbol = binance_symbol
        provider_interval = map_timeframe_to_binance_interval(signal.timeframe or "15m")
        candles_data = fetch_klines(
            symbol=provider_symbol,
            interval=provider_interval,
            start_time_ms=dt_to_ms(replay_start),
            end_time_ms=dt_to_ms(replay_end),
            limit=300,
            use_ui_klines=True,
        )

    # 2) GOLD / US100 via Twelve Data
    else:
        td_symbol = map_signal_asset_to_twelvedata_symbol(asset)
        if td_symbol:
            provider_symbol = td_symbol
            provider_interval = map_timeframe_to_twelvedata_interval(signal.timeframe or "15m")
            candles_data = fetch_time_series(
                symbol=provider_symbol,
                interval=provider_interval,
                start_date=replay_start,
                end_date=replay_end,
                outputsize=300,
                timezone="UTC",
            )

    if not candles_data:
        return None

    replay = signal.replay
    if not replay:
        replay = TradeReplay(
            signal_id=signal.id,
            symbol=provider_symbol or asset,
            timeframe=provider_interval or str(signal.timeframe or "15m"),
            direction=(signal.action or "BUY").upper(),
            replay_start=replay_start,
            replay_end=replay_end,
            entry_time=signal.created_at or datetime.utcnow(),
            exit_time=signal.closed_at,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            result=signal.status,
            result_percent=signal.result_percent,
            market_context=signal.reason,
            post_analysis=signal.reason,
        )
        db.session.add(replay)
        db.session.flush()
    else:
        replay.symbol = provider_symbol or asset
        replay.timeframe = provider_interval or str(signal.timeframe or "15m")
        replay.direction = (signal.action or "BUY").upper()
        replay.replay_start = replay_start
        replay.replay_end = replay_end
        replay.entry_time = signal.created_at or datetime.utcnow()
        replay.exit_time = signal.closed_at
        replay.entry_price = signal.entry_price
        replay.stop_loss = signal.stop_loss
        replay.take_profit = signal.take_profit
        replay.result = signal.status
        replay.result_percent = signal.result_percent
        replay.market_context = signal.reason
        replay.post_analysis = signal.reason

        ReplayCandle.query.filter_by(trade_replay_id=replay.id).delete()
        ReplayEvent.query.filter_by(trade_replay_id=replay.id).delete()
        db.session.flush()

    _insert_replay_candles(replay, candles_data)
    _create_replay_events(replay, signal, candles_data)

    db.session.commit()
    return replay


def _insert_replay_candles(replay: TradeReplay, candles_data: list[dict]) -> None:
    for row in candles_data:
        candle_time = _parse_candle_time(row)

        candle = ReplayCandle(
            trade_replay_id=replay.id,
            candle_time=candle_time,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]) if row.get("volume") not in [None, ""] else None,
            position_index=int(row["position_index"]),
        )
        db.session.add(candle)


def _parse_candle_time(row: dict) -> datetime:
    if "open_time" in row:
        return datetime.utcfromtimestamp(int(row["open_time"]) / 1000)

    if "time" in row:
        raw = row["time"]
        if isinstance(raw, datetime):
            return raw

        # Twelve Data style
        try:
            return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

        # ISO style fallback
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            pass

    return datetime.utcnow()


def _closest_index_by_price(candles_data: list[dict], target_price: float | None) -> int:
    if target_price is None or not candles_data:
        return 0

    best_idx = 0
    best_distance = float("inf")

    for row in candles_data:
        close_price = float(row["close"])
        distance = abs(close_price - float(target_price))
        if distance < best_distance:
            best_distance = distance
            best_idx = int(row["position_index"])

    return best_idx


def _event_time_from_index(candles_data: list[dict], idx: int) -> datetime:
    if not candles_data:
        return datetime.utcnow()

    idx = max(0, min(idx, len(candles_data) - 1))
    return _parse_candle_time(candles_data[idx])


def _create_replay_events(replay: TradeReplay, signal: Signal, candles_data: list[dict]) -> None:
    if not candles_data:
        return

    entry_idx = _closest_index_by_price(candles_data, signal.entry_price)
    tp_idx = (
        _closest_index_by_price(candles_data, signal.take_profit)
        if signal.take_profit is not None
        else min(len(candles_data) - 1, entry_idx + 20)
    )
    sl_idx = (
        _closest_index_by_price(candles_data, signal.stop_loss)
        if signal.stop_loss is not None
        else min(len(candles_data) - 1, entry_idx + 10)
    )
    context_idx = max(0, entry_idx - 3)
    decision_idx = min(len(candles_data) - 1, entry_idx + 8)

    events = [
        ReplayEvent(
            trade_replay_id=replay.id,
            event_time=_event_time_from_index(candles_data, context_idx),
            event_type="context",
            title="Observation du setup",
            description=signal.reason or "Contexte de marché exploitable avant activation du trade.",
            price_level=signal.entry_price,
            position_index=context_idx,
        ),
        ReplayEvent(
            trade_replay_id=replay.id,
            event_time=signal.created_at or _event_time_from_index(candles_data, entry_idx),
            event_type="entry",
            title="Entrée validée",
            description=f"Entrée {(signal.action or 'BUY').upper()} activée sur {signal.asset}.",
            price_level=signal.entry_price,
            position_index=entry_idx,
        ),
        ReplayEvent(
            trade_replay_id=replay.id,
            event_time=_event_time_from_index(candles_data, decision_idx),
            event_type="decision",
            title="Point de décision",
            description="Zone de respiration du marché avant développement du mouvement.",
            price_level=signal.entry_price,
            position_index=decision_idx,
        ),
    ]

    if signal.status == "WIN" and signal.take_profit is not None:
        events.append(
            ReplayEvent(
                trade_replay_id=replay.id,
                event_time=signal.closed_at or _event_time_from_index(candles_data, tp_idx),
                event_type="tp_hit",
                title="Take Profit atteint",
                description="Le scénario s’est développé en faveur du plan initial.",
                price_level=signal.take_profit,
                position_index=tp_idx,
            )
        )
    elif signal.status == "LOSS" and signal.stop_loss is not None:
        events.append(
            ReplayEvent(
                trade_replay_id=replay.id,
                event_time=signal.closed_at or _event_time_from_index(candles_data, sl_idx),
                event_type="sl_hit",
                title="Stop Loss atteint",
                description="Le scénario a invalidé le plan initial.",
                price_level=signal.stop_loss,
                position_index=sl_idx,
            )
        )

    for event in events:
        db.session.add(event)