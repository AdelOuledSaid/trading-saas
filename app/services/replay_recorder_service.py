from datetime import datetime, timedelta
from typing import Optional

from flask import has_request_context, request

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


SUPPORTED_LANGS = {"fr", "en", "es", "de", "it", "pt", "ru"}


REPLAY_TEXTS = {
    "setup_observation": {
        "fr": "Observation du setup",
        "en": "Setup Observation",
        "es": "Observación del setup",
        "de": "Setup-Beobachtung",
        "it": "Osservazione del setup",
        "pt": "Observação do setup",
        "ru": "Наблюдение за сетапом",
    },
    "market_context": {
        "fr": "Contexte de marché exploitable avant activation du trade.",
        "en": "Actionable market context before trade activation.",
        "es": "Contexto de mercado utilizable antes de la activación de la operación.",
        "de": "Nutzbarer Marktkontext vor der Aktivierung des Trades.",
        "it": "Contesto di mercato utilizzabile prima dell’attivazione del trade.",
        "pt": "Contexto de mercado acionável antes da ativação do trade.",
        "ru": "Рабочий рыночный контекст перед активацией сделки.",
    },
    "entry_confirmed": {
        "fr": "Entrée validée",
        "en": "Entry Confirmed",
        "es": "Entrada confirmada",
        "de": "Einstieg bestätigt",
        "it": "Entrata confermata",
        "pt": "Entrada confirmada",
        "ru": "Вход подтвержден",
    },
    "entry_activated": {
        "fr": "Entrée {direction} activée sur {asset}.",
        "en": "{direction} entry activated on {asset}.",
        "es": "Entrada {direction} activada en {asset}.",
        "de": "{direction}-Einstieg auf {asset} aktiviert.",
        "it": "Entrata {direction} attivata su {asset}.",
        "pt": "Entrada {direction} ativada em {asset}.",
        "ru": "Вход {direction} активирован по {asset}.",
    },
    "decision_point": {
        "fr": "Point de décision",
        "en": "Decision Point",
        "es": "Punto de decisión",
        "de": "Entscheidungspunkt",
        "it": "Punto decisionale",
        "pt": "Ponto de decisão",
        "ru": "Точка принятия решения",
    },
    "decision_zone": {
        "fr": "Zone de respiration du marché avant développement du mouvement.",
        "en": "Market pause zone before the move develops.",
        "es": "Zona de pausa del mercado antes del desarrollo del movimiento.",
        "de": "Markt-Atempause vor der Fortsetzung der Bewegung.",
        "it": "Zona di pausa del mercato prima dello sviluppo del movimento.",
        "pt": "Zona de pausa do mercado antes do desenvolvimento do movimento.",
        "ru": "Зона рыночной паузы перед развитием движения.",
    },
    "tp_hit": {
        "fr": "Take Profit atteint",
        "en": "Take Profit Hit",
        "es": "Take Profit alcanzado",
        "de": "Take Profit erreicht",
        "it": "Take Profit raggiunto",
        "pt": "Take Profit atingido",
        "ru": "Take Profit достигнут",
    },
    "tp_description": {
        "fr": "Le scénario s’est développé en faveur du plan initial.",
        "en": "The scenario played out in favor of the initial plan.",
        "es": "El escenario se desarrolló a favor del plan inicial.",
        "de": "Das Szenario entwickelte sich zugunsten des ursprünglichen Plans.",
        "it": "Lo scenario si è sviluppato a favore del piano iniziale.",
        "pt": "O cenário evoluiu a favor do plano inicial.",
        "ru": "Сценарий развился в пользу первоначального плана.",
    },
    "sl_hit": {
        "fr": "Stop Loss atteint",
        "en": "Stop Loss Hit",
        "es": "Stop Loss alcanzado",
        "de": "Stop Loss erreicht",
        "it": "Stop Loss raggiunto",
        "pt": "Stop Loss atingido",
        "ru": "Stop Loss достигнут",
    },
    "sl_description": {
        "fr": "Le scénario a invalidé le plan initial.",
        "en": "The scenario invalidated the initial plan.",
        "es": "El escenario invalidó el plan inicial.",
        "de": "Das Szenario hat den ursprünglichen Plan invalidiert.",
        "it": "Lo scenario ha invalidato il piano iniziale.",
        "pt": "O cenário invalidou o plano inicial.",
        "ru": "Сценарий отменил первоначальный план.",
    },
}


def _get_active_lang() -> str:
    lang = "en"

    if has_request_context():
        lang = (
            request.args.get("lang_code")
            or (request.view_args or {}).get("lang_code")
            or "en"
        )

    lang = str(lang or "en").lower()
    return lang if lang in SUPPORTED_LANGS else "en"


def _rt(key: str, lang: str | None = None, **kwargs) -> str:
    active_lang = (lang or _get_active_lang()).lower()

    if active_lang not in SUPPORTED_LANGS:
        active_lang = "en"

    value = REPLAY_TEXTS.get(key, {}).get(active_lang)

    if not value:
        value = REPLAY_TEXTS.get(key, {}).get("en", key)

    try:
        return value.format(**kwargs)
    except Exception:
        return value


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

    lang = _get_active_lang()

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

    direction = (signal.action or "BUY").upper()
    asset = signal.asset or replay.symbol or "-"

    events = [
        ReplayEvent(
            trade_replay_id=replay.id,
            event_time=_event_time_from_index(candles_data, context_idx),
            event_type="context",
            title=_rt("setup_observation", lang),
            description=signal.reason or _rt("market_context", lang),
            price_level=signal.entry_price,
            position_index=context_idx,
        ),
        ReplayEvent(
            trade_replay_id=replay.id,
            event_time=signal.created_at or _event_time_from_index(candles_data, entry_idx),
            event_type="entry",
            title=_rt("entry_confirmed", lang),
            description=_rt("entry_activated", lang, direction=direction, asset=asset),
            price_level=signal.entry_price,
            position_index=entry_idx,
        ),
        ReplayEvent(
            trade_replay_id=replay.id,
            event_time=_event_time_from_index(candles_data, decision_idx),
            event_type="decision",
            title=_rt("decision_point", lang),
            description=_rt("decision_zone", lang),
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
                title=_rt("tp_hit", lang),
                description=_rt("tp_description", lang),
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
                title=_rt("sl_hit", lang),
                description=_rt("sl_description", lang),
                price_level=signal.stop_loss,
                position_index=sl_idx,
            )
        )

    for event in events:
        db.session.add(event)