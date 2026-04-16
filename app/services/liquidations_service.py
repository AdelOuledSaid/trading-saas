from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from threading import Lock, Thread
from typing import List, Dict, Any, Optional
import json
import time

from websocket import WebSocketApp


@dataclass
class LiquidationEvent:
    asset: str
    side: str
    exchange: str
    price: str
    value_usd: str
    value_usd_number: float
    quantity: str
    timeframe: str
    impact: str
    market_bias: str
    time: str
    timestamp: str
    score: int


class LiquidationsService:
    WS_URL = "wss://fstream.binance.com/ws/!forceOrder@arr"
    SUPPORTED_ASSETS = {"BTC", "ETH", "SOL", "XRP", "BNB"}

    _events: List[LiquidationEvent] = []
    _lock = Lock()
    _started = False
    _max_events = 200

    def __init__(self) -> None:
        self._ensure_started()

    @classmethod
    def _ensure_started(cls) -> None:
        if cls._started:
            return
        cls._started = True
        thread = Thread(target=cls._run_ws_forever, daemon=True)
        thread.start()

    @classmethod
    def _run_ws_forever(cls) -> None:
        while True:
            try:
                print("[Liquidations] Connecting Binance WS...")
                ws = WebSocketApp(
                    cls.WS_URL,
                    on_message=cls._on_message,
                    on_error=cls._on_error,
                    on_close=cls._on_close,
                )
                ws.run_forever(ping_interval=120, ping_timeout=30)
            except Exception as e:
                print(f"[Liquidations] WS fatal error: {e}")
            time.sleep(5)

    @classmethod
    def _on_message(cls, ws, message: str) -> None:
        try:
            payload = json.loads(message)
            order = payload.get("o", {})
            symbol = order.get("s", "")

            if not symbol.endswith("USDT"):
                return

            asset = symbol.replace("USDT", "").upper()
            if asset not in cls.SUPPORTED_ASSETS:
                return

            side_raw = order.get("S", "")
            side = "Short" if side_raw == "SELL" else "Long"

            avg_price = cls._to_float(order.get("ap")) or cls._to_float(order.get("p"))
            qty = cls._to_float(order.get("z")) or cls._to_float(order.get("q"))
            value_usd_number = avg_price * qty

            if value_usd_number <= 0:
                return

            impact = cls._impact_from_value(value_usd_number)
            market_bias = "Bullish" if side == "Short" else "Bearish"
            score = cls._score_from_event(value_usd_number, impact)

            trade_ts = order.get("T") or payload.get("E")
            event_dt = cls._ts_to_datetime(trade_ts)

            event = LiquidationEvent(
                asset=asset,
                side=side,
                exchange="Binance",
                price=cls._format_price(avg_price, asset),
                value_usd=cls._format_usd(value_usd_number),
                value_usd_number=value_usd_number,
                quantity=cls._format_quantity(qty, asset),
                timeframe="Live",
                impact=impact,
                market_bias=market_bias,
                time="Just now",
                timestamp=event_dt.isoformat(),
                score=score,
            )

            with cls._lock:
                cls._events.insert(0, event)
                cls._events = cls._events[: cls._max_events]

        except Exception as e:
            print(f"[Liquidations] Parse error: {e}")

    @classmethod
    def _on_error(cls, ws, error) -> None:
        print(f"[Liquidations] WS error: {error}")

    @classmethod
    def _on_close(cls, ws, close_status_code, close_msg) -> None:
        print(f"[Liquidations] WS closed: {close_status_code} - {close_msg}")

    def _get_all_events(self) -> List[LiquidationEvent]:
        with self._lock:
            live_events = list(self._events)

        if live_events:
            for e in live_events:
                e.time = self._humanize_timestamp(e.timestamp)
            return live_events

        return self._load_mock_events()

    def get_events(
        self,
        asset: Optional[str] = None,
        side: Optional[str] = None,
        only_high_impact: bool = False,
        limit: int = 20,
    ) -> List[LiquidationEvent]:
        events = self._get_all_events()

        if asset:
            asset = asset.upper().strip()
            events = [e for e in events if e.asset == asset]

        if side:
            side = side.lower().strip()
            if side in {"long", "short"}:
                events = [e for e in events if e.side.lower() == side]

        if only_high_impact:
            events = [e for e in events if e.impact == "High"]

        events = sorted(events, key=lambda x: (x.score, x.timestamp), reverse=True)
        return events[:limit]

    def get_events_dict(
        self,
        asset: Optional[str] = None,
        side: Optional[str] = None,
        only_high_impact: bool = False,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        return [
            asdict(event)
            for event in self.get_events(
                asset=asset,
                side=side,
                only_high_impact=only_high_impact,
                limit=limit,
            )
        ]

    def get_summary(self) -> Dict[str, Any]:
        events = self._get_all_events()

        if not events:
            return {
                "total_events": 0,
                "total_value": "$0.0M",
                "long_value": "$0.0M",
                "short_value": "$0.0M",
                "long_value_numeric": 0,
                "short_value_numeric": 0,
                "long_count": 0,
                "short_count": 0,
                "high_impact_count": 0,
                "dominant_bias": "Neutral",
                "pressure_ratio": 50,
                "market_state": "Waiting live feed",
                "imbalance_strength": "Weak",
                "biggest_asset": "BTC",
                "biggest_value": "$0.0M",
                "biggest_side": "Long",
                "biggest_exchange": "Binance",
            }

        total_value = sum(e.value_usd_number for e in events)
        long_events = [e for e in events if e.side == "Long"]
        short_events = [e for e in events if e.side == "Short"]

        long_value = sum(e.value_usd_number for e in long_events)
        short_value = sum(e.value_usd_number for e in short_events)

        long_count = len(long_events)
        short_count = len(short_events)
        high_impact_count = sum(1 for e in events if e.impact == "High")

        total_liq = long_value + short_value
        if total_liq > 0:
            short_pressure = (short_value / total_liq) * 100
            long_pressure = (long_value / total_liq) * 100
        else:
            short_pressure = 50
            long_pressure = 50

        if short_value > long_value * 1.2:
            dominant_bias = "Bullish Squeeze"
        elif long_value > short_value * 1.2:
            dominant_bias = "Bearish Flush"
        else:
            dominant_bias = "Neutral Range"

        diff = abs(short_pressure - long_pressure)
        if diff > 30:
            imbalance_strength = "Extreme"
        elif diff > 15:
            imbalance_strength = "Strong"
        elif diff > 5:
            imbalance_strength = "Moderate"
        else:
            imbalance_strength = "Weak"

        if dominant_bias == "Bullish Squeeze" and high_impact_count >= 3:
            market_state = "Aggressive Short Squeeze"
        elif dominant_bias == "Bearish Flush" and high_impact_count >= 3:
            market_state = "Capitulation Phase"
        elif imbalance_strength == "Extreme":
            market_state = "High Volatility Imbalance"
        else:
            market_state = "Balanced / Transition"

        biggest = max(events, key=lambda e: e.value_usd_number)

        return {
            "total_events": len(events),
            "total_value": self._format_usd(total_value),
            "long_value": self._format_usd(long_value),
            "short_value": self._format_usd(short_value),
            "long_value_numeric": long_value,
            "short_value_numeric": short_value,
            "long_count": long_count,
            "short_count": short_count,
            "high_impact_count": high_impact_count,
            "dominant_bias": dominant_bias,
            "pressure_ratio": round(short_pressure),
            "market_state": market_state,
            "imbalance_strength": imbalance_strength,
            "biggest_asset": biggest.asset,
            "biggest_value": biggest.value_usd,
            "biggest_side": biggest.side,
            "biggest_exchange": biggest.exchange,
        }

    def get_top_events(self, limit: int = 5) -> List[Dict[str, Any]]:
        events = sorted(self._get_all_events(), key=lambda e: e.value_usd_number, reverse=True)
        return [asdict(e) for e in events[:limit]]

    def _load_mock_events(self) -> List[LiquidationEvent]:
        now = datetime.now(timezone.utc)

        raw = [
            ("BTC", "Short", "Binance", 68420, 12_800_000, 187, "1m", "High", "Bullish", 8, 11),
            ("ETH", "Long", "Bybit", 3448, 8_600_000, 2495, "5m", "High", "Bearish", 7, 16),
            ("SOL", "Short", "OKX", 182.4, 5_200_000, 28500, "15m", "Medium", "Bullish", 6, 24),
            ("BTC", "Long", "Binance", 67990, 14_300_000, 210, "1m", "High", "Bearish", 9, 28),
            ("ETH", "Short", "Bybit", 3492, 6_400_000, 1830, "5m", "Medium", "Bullish", 6, 34),
            ("BNB", "Long", "Binance", 602.5, 3_100_000, 5145, "15m", "Medium", "Bearish", 5, 41),
            ("SOL", "Long", "Bybit", 178.6, 4_700_000, 26300, "5m", "Medium", "Bearish", 5, 49),
            ("XRP", "Short", "OKX", 0.84, 2_900_000, 3450000, "15m", "Low", "Bullish", 4, 58),
            ("BTC", "Short", "Bybit", 68610, 9_200_000, 134, "1m", "High", "Bullish", 8, 65),
            ("ETH", "Long", "OKX", 3415, 7_100_000, 2078, "5m", "High", "Bearish", 7, 73),
            ("BNB", "Short", "Binance", 611.7, 2_400_000, 3925, "15m", "Low", "Bullish", 4, 85),
            ("BTC", "Long", "OKX", 67680, 11_600_000, 171, "1m", "High", "Bearish", 8, 94),
        ]

        events: List[LiquidationEvent] = []
        for asset, side, exchange, price, usd_value, qty, tf, impact, bias, score, mins_ago in raw:
            ts = now - timedelta(minutes=mins_ago)
            events.append(
                LiquidationEvent(
                    asset=asset,
                    side=side,
                    exchange=exchange,
                    price=self._format_price(price, asset),
                    value_usd=self._format_usd(usd_value),
                    value_usd_number=float(usd_value),
                    quantity=self._format_quantity(qty, asset),
                    timeframe=tf,
                    impact=impact,
                    market_bias=bias,
                    time=self._humanize_minutes(mins_ago),
                    timestamp=ts.isoformat(),
                    score=score,
                )
            )
        return events

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _ts_to_datetime(ms: Any) -> datetime:
        try:
            return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)

    @staticmethod
    def _impact_from_value(value: float) -> str:
        if value >= 5_000_000:
            return "High"
        if value >= 1_000_000:
            return "Medium"
        return "Low"

    @staticmethod
    def _score_from_event(value: float, impact: str) -> int:
        base = 1
        if impact == "High":
            base = 9
        elif impact == "Medium":
            base = 6
        elif impact == "Low":
            base = 3

        if value >= 10_000_000:
            base += 2
        elif value >= 5_000_000:
            base += 1

        return base

    @staticmethod
    def _format_usd(value: float) -> str:
        if value >= 1_000_000_000:
            return f"${value / 1_000_000_000:.2f}B"
        if value >= 1_000_000:
            return f"${value / 1_000_000:.1f}M"
        if value >= 1_000:
            return f"${value / 1_000:.1f}K"
        return f"${value:,.0f}"

    @staticmethod
    def _format_price(value: float, asset: str) -> str:
        if asset == "XRP":
            return f"${value:.4f}"
        return f"${value:,.2f}"

    @staticmethod
    def _format_quantity(value: float, asset: str) -> str:
        if asset in {"XRP", "SOL"}:
            return f"{value:,.0f} {asset}"
        if value >= 1000:
            return f"{value:,.0f} {asset}"
        return f"{value:,.3f} {asset}"

    @staticmethod
    def _humanize_minutes(mins_ago: int) -> str:
        if mins_ago < 60:
            return f"{mins_ago} min"
        hours = mins_ago // 60
        mins = mins_ago % 60
        if mins == 0:
            return f"{hours}h"
        return f"{hours}h {mins:02d}"

    @staticmethod
    def _humanize_timestamp(ts: str) -> str:
        try:
            dt = datetime.fromisoformat(ts)
            now = datetime.now(timezone.utc)
            diff = now - dt

            seconds = int(diff.total_seconds())
            if seconds < 60:
                return "Just now"

            minutes = seconds // 60
            if minutes < 60:
                return f"{minutes} min"

            hours = minutes // 60
            mins = minutes % 60
            if mins == 0:
                return f"{hours}h"
            return f"{hours}h {mins:02d}"
        except Exception:
            return "Recent"


service_instance = LiquidationsService()


def get_liquidations_service() -> LiquidationsService:
    return service_instance