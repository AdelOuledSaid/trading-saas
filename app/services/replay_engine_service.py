from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


# =========================
# DATA CLASSES
# =========================
@dataclass
class ReplayLevelHit:
    index: int | None
    time: str | None
    price: float | None
    reason: str | None


@dataclass
class ReplayEngineResult:
    entry_index: int
    entry_time: str | None
    decision_index: int
    decision_time: str | None
    exit_index: int
    exit_time: str | None
    exit_reason: str
    derived_result: str
    trade_health: str
    market_structure: str
    htf_bias: str
    distance_to_sl_percent: float | None
    distance_to_tp_percent: float | None
    max_favorable_excursion_percent: float | None
    max_adverse_excursion_percent: float | None
    live_outcome_if_hold: str
    decision_context: str
    should_stop_replay_at_exit: bool
    sl_hit: ReplayLevelHit
    tp_hit: ReplayLevelHit
    exit_price: float | None
    events: list[dict[str, Any]]
    timeline: list[dict[str, Any]]


# =========================
# BASIC HELPERS
# =========================
def _safe_float(value: Any, default: float | None = 0.0) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_iso(dt: Any) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)


def _safe_timestamp(value: Any) -> float | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.timestamp()

    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except Exception:
        return None


def _candle_time(candle: dict[str, Any]) -> str | None:
    return candle.get("time")


def _candle_ts(candle: dict[str, Any]) -> float | None:
    return _safe_timestamp(_candle_time(candle))


def _percent_distance(a: float | None, b: float | None) -> float | None:
    if a in [None, 0] or b is None:
        return None
    try:
        return round(((b - a) / a) * 100, 2)
    except Exception:
        return None


# =========================
# MARKET STRUCTURE
# =========================
def _infer_market_structure(candles: list[dict[str, Any]]) -> str:
    if not candles or len(candles) < 6:
        return "neutral"

    highs = [_safe_float(c["high"], 0.0) for c in candles[-8:]]
    lows = [_safe_float(c["low"], 0.0) for c in candles[-8:]]

    if len(highs) < 4 or len(lows) < 4:
        return "neutral"

    recent_highs_up = highs[-1] > highs[-3] > highs[-5]
    recent_lows_up = lows[-1] > lows[-3] > lows[-5]

    recent_highs_down = highs[-1] < highs[-3] < highs[-5]
    recent_lows_down = lows[-1] < lows[-3] < lows[-5]

    if recent_highs_up and recent_lows_up:
        return "bullish"
    if recent_highs_down and recent_lows_down:
        return "bearish"
    return "range"


def _infer_htf_bias(htf_candles: list[dict[str, Any]]) -> str:
    if not htf_candles or len(htf_candles) < 2:
        return "NEUTRAL"

    first_close = _safe_float(htf_candles[0].get("close"), 0.0)
    last_close = _safe_float(htf_candles[-1].get("close"), 0.0)

    if first_close is None or last_close is None:
        return "NEUTRAL"

    if last_close > first_close:
        return "BULLISH"
    if last_close < first_close:
        return "BEARISH"
    return "NEUTRAL"


# =========================
# INDEX FINDERS
# =========================
def _find_index_by_time(candles: list[dict[str, Any]], target_time: Any) -> int | None:
    target_ts = _safe_timestamp(target_time)
    if target_ts is None or not candles:
        return None

    best_idx = None
    best_diff = None

    for candle in candles:
        idx = int(candle.get("index", 0))
        c_ts = _candle_ts(candle)
        if c_ts is None:
            continue

        diff = abs(c_ts - target_ts)
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_idx = idx

    return best_idx


def _find_index_by_price(candles: list[dict[str, Any]], target_price: float | None) -> int | None:
    target = _safe_float(target_price, None)
    if target is None or not candles:
        return None

    best_idx = None
    best_diff = None

    for candle in candles:
        idx = int(candle.get("index", 0))
        close_price = _safe_float(candle.get("close"), None)
        if close_price is None:
            continue

        diff = abs(close_price - target)
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_idx = idx

    return best_idx


def _resolve_entry_index(
    candles: list[dict[str, Any]],
    entry_time: Any,
    entry_price: float | None,
) -> int:
    idx_by_time = _find_index_by_time(candles, entry_time)
    if idx_by_time is not None:
        return idx_by_time

    idx_by_price = _find_index_by_price(candles, entry_price)
    if idx_by_price is not None:
        return idx_by_price

    return 0


# =========================
# HIT DETECTION
# =========================
def _detect_level_hits(
    candles: list[dict[str, Any]],
    entry_index: int,
    direction: str,
    stop_loss: float | None,
    take_profit: float | None,
) -> tuple[ReplayLevelHit, ReplayLevelHit]:
    sl_hit = ReplayLevelHit(index=None, time=None, price=stop_loss, reason=None)
    tp_hit = ReplayLevelHit(index=None, time=None, price=take_profit, reason=None)

    if not candles:
        return sl_hit, tp_hit

    for candle in candles[entry_index:]:
        idx = int(candle.get("index", 0))
        low = _safe_float(candle.get("low"), None)
        high = _safe_float(candle.get("high"), None)
        c_time = _candle_time(candle)

        if direction == "BUY":
            if tp_hit.index is None and take_profit is not None and high is not None and high >= take_profit:
                tp_hit = ReplayLevelHit(
                    index=idx,
                    time=c_time,
                    price=take_profit,
                    reason="TP"
                )
            if sl_hit.index is None and stop_loss is not None and low is not None and low <= stop_loss:
                sl_hit = ReplayLevelHit(
                    index=idx,
                    time=c_time,
                    price=stop_loss,
                    reason="SL"
                )

        elif direction == "SELL":
            if tp_hit.index is None and take_profit is not None and low is not None and low <= take_profit:
                tp_hit = ReplayLevelHit(
                    index=idx,
                    time=c_time,
                    price=take_profit,
                    reason="TP"
                )
            if sl_hit.index is None and stop_loss is not None and high is not None and high >= stop_loss:
                sl_hit = ReplayLevelHit(
                    index=idx,
                    time=c_time,
                    price=stop_loss,
                    reason="SL"
                )

        if tp_hit.index is not None and sl_hit.index is not None:
            break

    return sl_hit, tp_hit


def _resolve_exit_from_hits(
    direction: str,
    sl_hit: ReplayLevelHit,
    tp_hit: ReplayLevelHit,
    fallback_result: str,
    candles: list[dict[str, Any]],
) -> tuple[int, str, float | None, str]:
    fallback_result = (fallback_result or "OPEN").upper()

    if tp_hit.index is not None and sl_hit.index is not None:
        if tp_hit.index < sl_hit.index:
            return tp_hit.index, "TP", tp_hit.price, "WIN"
        if sl_hit.index < tp_hit.index:
            return sl_hit.index, "SL", sl_hit.price, "LOSS"

        if direction == "BUY":
            return sl_hit.index, "SL", sl_hit.price, "LOSS"
        return sl_hit.index, "SL", sl_hit.price, "LOSS"

    if tp_hit.index is not None:
        return tp_hit.index, "TP", tp_hit.price, "WIN"

    if sl_hit.index is not None:
        return sl_hit.index, "SL", sl_hit.price, "LOSS"

    if not candles:
        return 0, "OPEN", None, fallback_result

    final_idx = int(candles[-1].get("index", 0))
    final_close = _safe_float(candles[-1].get("close"), None)
    return final_idx, "OPEN", final_close, fallback_result


# =========================
# TRADE HEALTH / DECISION
# =========================
def _compute_trade_health(
    direction: str,
    last_price: float | None,
    entry_price: float | None,
    stop_loss: float | None,
) -> str:
    if None in [last_price, entry_price, stop_loss]:
        return "unknown"

    entry = float(entry_price)
    sl = float(stop_loss)
    last = float(last_price)

    risk = abs(entry - sl)
    if risk <= 0:
        return "unknown"

    if direction == "BUY":
        adverse = max(0.0, entry - last)
    else:
        adverse = max(0.0, last - entry)

    ratio = adverse / risk

    if ratio < 0.35:
        return "healthy"
    if ratio < 0.8:
        return "under_pressure"
    if ratio < 1.0:
        return "critical"
    return "invalidated"


def _compute_decision_context(
    direction: str,
    trade_health: str,
    market_structure: str,
    htf_bias: str,
    distance_to_sl_percent: float | None,
    distance_to_tp_percent: float | None,
) -> str:
    parts = []

    parts.append(f"Direction {direction}.")
    parts.append(f"Structure locale {market_structure}.")
    parts.append(f"Biais HTF {htf_bias}.")

    if trade_health == "healthy":
        parts.append("Le trade reste sain.")
    elif trade_health == "under_pressure":
        parts.append("Le trade subit une pression modérée.")
    elif trade_health == "critical":
        parts.append("Le trade est proche de l’invalidation.")
    elif trade_health == "invalidated":
        parts.append("Le trade est techniquement invalidé.")
    else:
        parts.append("L’état du trade est incertain.")

    if distance_to_sl_percent is not None:
        parts.append(f"Distance au SL: {distance_to_sl_percent}%.")

    if distance_to_tp_percent is not None:
        parts.append(f"Distance au TP: {distance_to_tp_percent}%.")

    return " ".join(parts)


def _choose_decision_index(
    candles: list[dict[str, Any]],
    entry_index: int,
    exit_index: int,
    direction: str,
    entry_price: float | None,
    stop_loss: float | None,
    take_profit: float | None,
) -> int:
    if not candles:
        return 0

    if exit_index <= entry_index:
        return min(len(candles) - 1, entry_index + 1)

    max_index = min(exit_index - 1, len(candles) - 1)
    if max_index <= entry_index:
        return min(len(candles) - 1, entry_index + 1)

    risk = abs((_safe_float(entry_price, 0.0) or 0.0) - (_safe_float(stop_loss, 0.0) or 0.0))
    if risk <= 0:
        return min(max_index, entry_index + 8)

    for candle in candles[entry_index + 1:max_index + 1]:
        idx = int(candle.get("index", 0))
        close_p = _safe_float(candle.get("close"), None)
        low = _safe_float(candle.get("low"), None)
        high = _safe_float(candle.get("high"), None)

        if close_p is None:
            continue

        if direction == "BUY":
            pullback_to_entry = abs(close_p - float(entry_price)) <= risk * 0.35 if entry_price is not None else False
            near_sl = low is not None and stop_loss is not None and low <= stop_loss + (risk * 0.35)
            near_tp = high is not None and take_profit is not None and high >= take_profit - (risk * 0.35)
        else:
            pullback_to_entry = abs(close_p - float(entry_price)) <= risk * 0.35 if entry_price is not None else False
            near_sl = high is not None and stop_loss is not None and high >= stop_loss - (risk * 0.35)
            near_tp = low is not None and take_profit is not None and low <= take_profit + (risk * 0.35)

        if pullback_to_entry or near_sl or near_tp:
            return idx

    span = max_index - entry_index
    return min(max_index, entry_index + max(6, int(span * 0.4)))


# =========================
# EXCURSION
# =========================
def _compute_excursions(
    candles: list[dict[str, Any]],
    entry_index: int,
    exit_index: int,
    direction: str,
    entry_price: float | None,
) -> tuple[float | None, float | None]:
    entry = _safe_float(entry_price, None)
    if entry is None or entry == 0 or not candles:
        return None, None

    section = candles[entry_index:exit_index + 1]
    if not section:
        return None, None

    max_favorable = 0.0
    max_adverse = 0.0

    for candle in section:
        high = _safe_float(candle.get("high"), entry)
        low = _safe_float(candle.get("low"), entry)

        if direction == "BUY":
            favorable = ((high - entry) / entry) * 100
            adverse = ((entry - low) / entry) * 100
        else:
            favorable = ((entry - low) / entry) * 100
            adverse = ((high - entry) / entry) * 100

        max_favorable = max(max_favorable, favorable)
        max_adverse = max(max_adverse, adverse)

    return round(max_favorable, 2), round(max_adverse, 2)


# =========================
# EVENTS / TIMELINE
# =========================
def _build_events_and_timeline(
    entry_index: int,
    entry_time: str | None,
    entry_price: float | None,
    decision_index: int,
    decision_time: str | None,
    exit_index: int,
    exit_time: str | None,
    exit_reason: str,
    exit_price: float | None,
    derived_result: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events = [
        {
            "id": 1,
            "type": "entry",
            "title": "Entrée du trade",
            "description": "Point d’exécution du setup.",
            "price_level": entry_price,
            "index": entry_index,
            "time": entry_time,
        },
        {
            "id": 2,
            "type": "decision",
            "title": "Moment de décision",
            "description": "Le marché atteint une zone de gestion critique.",
            "price_level": entry_price,
            "index": decision_index,
            "time": decision_time,
        },
    ]

    exit_type = "open"
    exit_title = "Trade toujours actif"
    exit_description = "Le trade reste ouvert. Le replay est une lecture de gestion, pas une conclusion fermée."

    if exit_reason == "TP":
        exit_type = "tp_hit"
        exit_title = "Take Profit atteint"
        exit_description = "L’objectif a été touché."
    elif exit_reason == "SL":
        exit_type = "sl_hit"
        exit_title = "Stop Loss touché"
        exit_description = "Le scénario a été invalidé."
    elif derived_result == "BREAKEVEN":
        exit_type = "breakeven"
        exit_title = "Break-even"
        exit_description = "Sortie neutre, capital protégé."

    events.append({
        "id": 3,
        "type": exit_type,
        "title": exit_title,
        "description": exit_description,
        "price_level": exit_price,
        "index": exit_index,
        "time": exit_time,
    })

    timeline = [
        {"type": "entry", "label": "Entrée", "index": entry_index},
        {"type": "decision", "label": "Décision", "index": decision_index},
        {
            "type": "outcome",
            "label": "Trade actif" if exit_type == "open" else exit_title,
            "index": exit_index,
        },
    ]

    timeline.sort(key=lambda x: x["index"])
    return events, timeline


# =========================
# PUBLIC ENGINE
# =========================
def build_replay_engine_result(
    candles: list[dict[str, Any]],
    direction: str,
    entry_price: float | None,
    stop_loss: float | None,
    take_profit: float | None,
    entry_time: Any = None,
    base_result: str = "OPEN",
    htf_candles: list[dict[str, Any]] | None = None,
) -> ReplayEngineResult:
    candles = candles or []
    htf_candles = htf_candles or []
    direction = (direction or "BUY").upper()
    base_result = (base_result or "OPEN").upper()

    if not candles:
        return ReplayEngineResult(
            entry_index=0,
            entry_time=None,
            decision_index=0,
            decision_time=None,
            exit_index=0,
            exit_time=None,
            exit_reason="OPEN",
            derived_result=base_result,
            trade_health="unknown",
            market_structure="neutral",
            htf_bias="NEUTRAL",
            distance_to_sl_percent=None,
            distance_to_tp_percent=None,
            max_favorable_excursion_percent=None,
            max_adverse_excursion_percent=None,
            live_outcome_if_hold=base_result,
            decision_context="Aucune donnée bougie disponible.",
            should_stop_replay_at_exit=False,
            sl_hit=ReplayLevelHit(None, None, stop_loss, None),
            tp_hit=ReplayLevelHit(None, None, take_profit, None),
            exit_price=None,
            events=[],
            timeline=[],
        )

    entry_index = _resolve_entry_index(candles, entry_time, entry_price)
    entry_index = max(0, min(entry_index, len(candles) - 1))

    sl_hit, tp_hit = _detect_level_hits(
        candles=candles,
        entry_index=entry_index,
        direction=direction,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )

    exit_index, exit_reason, exit_price, derived_result = _resolve_exit_from_hits(
        direction=direction,
        sl_hit=sl_hit,
        tp_hit=tp_hit,
        fallback_result=base_result,
        candles=candles,
    )

    exit_index = max(entry_index, min(exit_index, len(candles) - 1))
    exit_time = _candle_time(candles[exit_index])

    decision_index = _choose_decision_index(
        candles=candles,
        entry_index=entry_index,
        exit_index=exit_index,
        direction=direction,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )
    decision_index = max(entry_index + 1 if entry_index < len(candles) - 1 else entry_index, decision_index)
    decision_index = min(decision_index, max(exit_index - 1, entry_index))
    decision_time = _candle_time(candles[decision_index])

    last_price_before_decision = _safe_float(candles[decision_index].get("close"), None)
    distance_to_sl_percent = _percent_distance(last_price_before_decision, stop_loss)
    distance_to_tp_percent = _percent_distance(last_price_before_decision, take_profit)

    market_structure = _infer_market_structure(candles[:decision_index + 1])
    htf_bias = _infer_htf_bias(htf_candles)
    trade_health = _compute_trade_health(
        direction=direction,
        last_price=last_price_before_decision,
        entry_price=entry_price,
        stop_loss=stop_loss,
    )

    mfe, mae = _compute_excursions(
        candles=candles,
        entry_index=entry_index,
        exit_index=exit_index,
        direction=direction,
        entry_price=entry_price,
    )

    decision_context = _compute_decision_context(
        direction=direction,
        trade_health=trade_health,
        market_structure=market_structure,
        htf_bias=htf_bias,
        distance_to_sl_percent=distance_to_sl_percent,
        distance_to_tp_percent=distance_to_tp_percent,
    )

    events, timeline = _build_events_and_timeline(
        entry_index=entry_index,
        entry_time=_candle_time(candles[entry_index]),
        entry_price=entry_price,
        decision_index=decision_index,
        decision_time=decision_time,
        exit_index=exit_index,
        exit_time=exit_time,
        exit_reason=exit_reason,
        exit_price=exit_price,
        derived_result=derived_result,
    )

    should_stop = exit_reason in ["TP", "SL", "BREAKEVEN"]

    return ReplayEngineResult(
        entry_index=entry_index,
        entry_time=_candle_time(candles[entry_index]),
        decision_index=decision_index,
        decision_time=decision_time,
        exit_index=exit_index,
        exit_time=exit_time,
        exit_reason=exit_reason,
        derived_result=derived_result,
        trade_health=trade_health,
        market_structure=market_structure,
        htf_bias=htf_bias,
        distance_to_sl_percent=distance_to_sl_percent,
        distance_to_tp_percent=distance_to_tp_percent,
        max_favorable_excursion_percent=mfe,
        max_adverse_excursion_percent=mae,
        live_outcome_if_hold=derived_result,
        decision_context=decision_context,
        should_stop_replay_at_exit=should_stop,
        sl_hit=sl_hit,
        tp_hit=tp_hit,
        exit_price=exit_price,
        events=events,
        timeline=timeline,
    )


# =========================
# SERIALIZER
# =========================
def replay_engine_result_to_dict(result: ReplayEngineResult) -> dict[str, Any]:
    return {
        "entry_index": result.entry_index,
        "entry_time": result.entry_time,
        "decision_index": result.decision_index,
        "decision_time": result.decision_time,
        "exit_index": result.exit_index,
        "exit_time": result.exit_time,
        "exit_reason": result.exit_reason,
        "derived_result": result.derived_result,
        "trade_health": result.trade_health,
        "market_structure": result.market_structure,
        "htf_bias": result.htf_bias,
        "distance_to_sl_percent": result.distance_to_sl_percent,
        "distance_to_tp_percent": result.distance_to_tp_percent,
        "max_favorable_excursion_percent": result.max_favorable_excursion_percent,
        "max_adverse_excursion_percent": result.max_adverse_excursion_percent,
        "live_outcome_if_hold": result.live_outcome_if_hold,
        "decision_context": result.decision_context,
        "should_stop_replay_at_exit": result.should_stop_replay_at_exit,
        "sl_hit": {
            "index": result.sl_hit.index,
            "time": result.sl_hit.time,
            "price": result.sl_hit.price,
            "reason": result.sl_hit.reason,
        },
        "tp_hit": {
            "index": result.tp_hit.index,
            "time": result.tp_hit.time,
            "price": result.tp_hit.price,
            "reason": result.tp_hit.reason,
        },
        "exit_price": result.exit_price,
        "events": result.events,
        "timeline": result.timeline,
    }