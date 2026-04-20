from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests


BINANCE_BASE_URL = "https://api.binance.com"
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"


@dataclass
class AnalysisResult:
    token: str
    symbol: str
    interval: str
    indicator: str
    current_price: float
    market_cap: Optional[float]
    volume_24h: Optional[float]
    price_change_24h: Optional[float]
    signal: str
    bias: str
    confidence: int
    summary_context: Dict[str, Any]
    levels: Dict[str, float]
    indicators: Dict[str, Any]
    watchlist: List[Dict[str, Any]]
    trending: List[Dict[str, Any]]
    chart_series: Dict[str, List[float]]
    orderflow: Dict[str, Any]
    setup_replay: Dict[str, Any]
    multi_timeframe: Optional[Dict[str, Any]] = None
    premium: Optional[Dict[str, Any]] = None
    vip: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "token": self.token,
            "symbol": self.symbol,
            "interval": self.interval,
            "indicator": self.indicator,
            "current_price": self.current_price,
            "market_cap": self.market_cap,
            "volume_24h": self.volume_24h,
            "price_change_24h": self.price_change_24h,
            "signal": self.signal,
            "bias": self.bias,
            "confidence": self.confidence,
            "summary_context": self.summary_context,
            "levels": self.levels,
            "indicators": self.indicators,
            "watchlist": self.watchlist,
            "trending": self.trending,
            "chart_series": self.chart_series,
            "orderflow": self.orderflow,
            "setup_replay": self.setup_replay,
            "multi_timeframe": self.multi_timeframe,
            "premium": self.premium,
            "vip": self.vip,
        }


class SimpleTTLCache:
    def __init__(self, ttl_seconds: int = 60) -> None:
        self.ttl_seconds = ttl_seconds
        self._store: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str) -> Any:
        item = self._store.get(key)
        if not item:
            return None
        ts, value = item
        if time.time() - ts > self.ttl_seconds:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.time(), value)


class SetupReplayStore:
    def __init__(self, filepath: Optional[str] = None, limit: int = 500) -> None:
        base_dir = Path(os.getenv("TA_DATA_DIR", ".")).resolve()
        base_dir.mkdir(parents=True, exist_ok=True)
        self.filepath = Path(filepath or (base_dir / "setup_replay.json"))
        self.limit = limit

    def _load(self) -> List[Dict[str, Any]]:
        if not self.filepath.exists():
            return []
        try:
            return json.loads(self.filepath.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self, rows: List[Dict[str, Any]]) -> None:
        clipped = rows[-self.limit :]
        self.filepath.write_text(
            json.dumps(clipped, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def record_setup(self, row: Dict[str, Any]) -> None:
        rows = self._load()
        rows.append(row)
        self._save(rows)

    def get_history(self, token: str, interval: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        rows = self._load()
        filtered = [
            r for r in rows
            if r.get("token") == token and (interval is None or r.get("interval") == interval)
        ]
        return filtered[-limit:]

    def summarize(self, token: str, interval: Optional[str] = None) -> Dict[str, Any]:
        rows = self.get_history(token=token, interval=interval, limit=200)
        if not rows:
            return {
                "count": 0,
                "winrate": None,
                "avg_confidence": None,
                "last_setups": [],
                "best_bias": None,
            }

        wins = 0
        scored = 0
        bullish = 0
        bearish = 0
        confidences: List[float] = []

        for row in rows:
            confidences.append(float(row.get("confidence", 0)))
            outcome = row.get("simulated_outcome_pct")
            if outcome is not None:
                scored += 1
                if float(outcome) > 0:
                    wins += 1

            if row.get("bias") == "bullish":
                bullish += 1
            elif row.get("bias") == "bearish":
                bearish += 1

        best_bias = "bullish" if bullish > bearish else "bearish" if bearish > bullish else "mixed"

        return {
            "count": len(rows),
            "winrate": round((wins / scored) * 100, 2) if scored else None,
            "avg_confidence": round(sum(confidences) / len(confidences), 2) if confidences else None,
            "last_setups": rows[-5:],
            "best_bias": best_bias,
        }


class TechnicalAnalysisService:
    TOKEN_MAP = {
        "BTC": {"coingecko_id": "bitcoin", "binance_symbol": "BTCUSDT"},
        "ETH": {"coingecko_id": "ethereum", "binance_symbol": "ETHUSDT"},
        "XRP": {"coingecko_id": "ripple", "binance_symbol": "XRPUSDT"},
        "SOL": {"coingecko_id": "solana", "binance_symbol": "SOLUSDT"},
        "BNB": {"coingecko_id": "binancecoin", "binance_symbol": "BNBUSDT"},
        "DOGE": {"coingecko_id": "dogecoin", "binance_symbol": "DOGEUSDT"},
    }

    SUPPORTED_INTERVALS = {"15m", "1h", "4h", "1d"}
    SUPPORTED_INDICATORS = {"rsi", "stochasticrsi", "mfi", "ema", "macd"}
    MULTI_TIMEFRAMES = ("15m", "1h", "4h", "1d")

    _cg_cache = SimpleTTLCache(ttl_seconds=90)
    _analysis_cache = SimpleTTLCache(ttl_seconds=20)

    def __init__(self) -> None:
        self.session = requests.Session()
        self.coingecko_api_key = os.getenv("COINGECKO_API_KEY", "").strip()
        self.replay_store = SetupReplayStore()

    def get_available_tokens(self) -> List[Dict[str, str]]:
        return [
            {
                "token": token,
                "coingecko_id": meta["coingecko_id"],
                "symbol": meta["binance_symbol"],
            }
            for token, meta in self.TOKEN_MAP.items()
        ]

    def analyze(self, token: str, interval: str, indicator: str, include_multi_tf: bool = True) -> AnalysisResult:
        token = (token or "BTC").upper().strip()
        interval = (interval or "1h").lower().strip()
        indicator = (indicator or "stochasticrsi").lower().strip()

        if token not in self.TOKEN_MAP:
            token = "BTC"
        if interval not in self.SUPPORTED_INTERVALS:
            interval = "1h"
        if indicator not in self.SUPPORTED_INDICATORS:
            indicator = "stochasticrsi"

        cache_key = f"analyze:{token}:{interval}:{indicator}:{include_multi_tf}"
        cached = self._analysis_cache.get(cache_key)
        if cached is not None:
            return cached

        meta = self.TOKEN_MAP[token]
        candles = self._get_binance_klines(meta["binance_symbol"], interval=interval, limit=250)
        df = self._build_dataframe(candles)

        indicators = self._compute_indicators(df)
        levels = self._compute_levels(df)
        chart_series = self._build_chart_series(df)
        orderflow = self._simulate_orderflow(df)
        signal, bias, confidence = self._build_signal(indicators, indicator, orderflow)
        volatility = self._compute_volatility(df)

        cg_data = self._get_coin_market_safe(
            meta["coingecko_id"],
            fallback_price=float(df["close"].iloc[-1]),
        )
        watchlist = self.get_watchlist_safe()
        trending = self.get_trending_safe()

        summary_context = {
            "token": token,
            "symbol": meta["binance_symbol"],
            "interval": interval,
            "indicator": indicator,
            "price": float(df["close"].iloc[-1]),
            "price_change_24h": cg_data.get("price_change_percentage_24h"),
            "rsi": indicators["rsi"],
            "stochastic_rsi_k": indicators["stochastic_rsi_k"],
            "stochastic_rsi_d": indicators["stochastic_rsi_d"],
            "mfi": indicators["mfi"],
            "ema_20": indicators["ema_20"],
            "ema_50": indicators["ema_50"],
            "macd": indicators["macd"],
            "macd_signal": indicators["macd_signal"],
            "trend": indicators["trend"],
            "volume_trend": indicators["volume_trend"],
            "levels": levels,
            "signal": signal,
            "bias": bias,
            "confidence": confidence,
            "orderflow_state": orderflow["state"],
            "orderflow_strength": orderflow["strength"],
            "absorption": orderflow["absorption"],
            "volatility": volatility,
        }

        multi_timeframe = self.multi_timeframe_analysis(token=token, primary_indicator=indicator) if include_multi_tf else None
        premium = self._build_premium_payload(
            token=token,
            interval=interval,
            indicators=indicators,
            orderflow=orderflow,
            levels=levels,
            multi_timeframe=multi_timeframe,
        )
        vip = self._build_vip_payload(
            token=token,
            interval=interval,
            indicators=indicators,
            orderflow=orderflow,
            levels=levels,
            signal=signal,
            bias=bias,
            confidence=confidence,
            multi_timeframe=multi_timeframe,
            volatility=volatility,
        )

        setup_replay = self._record_and_build_setup_replay(
            token=token,
            interval=interval,
            signal=signal,
            bias=bias,
            confidence=confidence,
            current_price=float(df["close"].iloc[-1]),
            orderflow=orderflow,
            multi_timeframe=multi_timeframe,
        )

        result = AnalysisResult(
            token=token,
            symbol=meta["binance_symbol"],
            interval=interval,
            indicator=indicator,
            current_price=float(df["close"].iloc[-1]),
            market_cap=cg_data.get("market_cap"),
            volume_24h=cg_data.get("total_volume"),
            price_change_24h=cg_data.get("price_change_percentage_24h"),
            signal=signal,
            bias=bias,
            confidence=confidence,
            summary_context=summary_context,
            levels=levels,
            indicators=indicators,
            watchlist=watchlist,
            trending=trending,
            chart_series=chart_series,
            orderflow=orderflow,
            setup_replay=setup_replay,
            multi_timeframe=multi_timeframe,
            premium=premium,
            vip=vip,
        )

        self._analysis_cache.set(cache_key, result)
        return result

    def multi_timeframe_analysis(self, token: str, primary_indicator: str = "stochasticrsi") -> Dict[str, Any]:
        token = (token or "BTC").upper().strip()
        results: Dict[str, Dict[str, Any]] = {}

        for tf in self.MULTI_TIMEFRAMES:
            meta = self.TOKEN_MAP[token]
            candles = self._get_binance_klines(meta["binance_symbol"], interval=tf, limit=250)
            df = self._build_dataframe(candles)
            indicators = self._compute_indicators(df)
            levels = self._compute_levels(df)
            orderflow = self._simulate_orderflow(df)
            signal, bias, confidence = self._build_signal(indicators, primary_indicator, orderflow)

            results[tf] = {
                "price": float(df["close"].iloc[-1]),
                "signal": signal,
                "bias": bias,
                "confidence": confidence,
                "trend": indicators["trend"],
                "rsi": indicators["rsi"],
                "mfi": indicators["mfi"],
                "macd": indicators["macd"],
                "macd_signal": indicators["macd_signal"],
                "volume_trend": indicators["volume_trend"],
                "orderflow_state": orderflow["state"],
                "orderflow_strength": orderflow["strength"],
                "levels": levels,
            }

        confluence = self._build_confluence(results)

        return {
            "timeframes": results,
            "confluence": confluence,
        }

    def get_watchlist_safe(self) -> List[Dict[str, Any]]:
        cache_key = "watchlist"
        cached = self._cg_cache.get(cache_key)
        if cached is not None:
            return cached

        ids = ",".join(
            [
                self.TOKEN_MAP["BTC"]["coingecko_id"],
                self.TOKEN_MAP["ETH"]["coingecko_id"],
                self.TOKEN_MAP["XRP"]["coingecko_id"],
                self.TOKEN_MAP["SOL"]["coingecko_id"],
            ]
        )

        url = f"{COINGECKO_BASE_URL}/coins/markets"
        params = {
            "vs_currency": "usd",
            "ids": ids,
            "price_change_percentage": "24h",
            "sparkline": "false",
        }

        try:
            resp = self.session.get(url, params=params, headers=self._cg_headers(), timeout=15)
            if resp.status_code == 429:
                return cached or []
            resp.raise_for_status()
            rows = resp.json()
            result = [
                {
                    "symbol": row.get("symbol", "").upper(),
                    "name": row.get("name"),
                    "price": row.get("current_price"),
                    "change_24h": row.get("price_change_percentage_24h"),
                    "image": row.get("image"),
                }
                for row in rows
            ]
            self._cg_cache.set(cache_key, result)
            return result
        except Exception:
            return cached or []

    def get_trending_safe(self) -> List[Dict[str, Any]]:
        cache_key = "trending"
        cached = self._cg_cache.get(cache_key)
        if cached is not None:
            return cached

        url = f"{COINGECKO_BASE_URL}/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "volume_desc",
            "per_page": 6,
            "page": 1,
            "sparkline": "false",
            "price_change_percentage": "24h",
        }

        try:
            resp = self.session.get(url, params=params, headers=self._cg_headers(), timeout=15)
            if resp.status_code == 429:
                return cached or []
            resp.raise_for_status()
            rows = resp.json()
            result = [
                {
                    "symbol": row.get("symbol", "").upper(),
                    "name": row.get("name"),
                    "price": row.get("current_price"),
                    "change_24h": row.get("price_change_percentage_24h"),
                    "market_cap_rank": row.get("market_cap_rank"),
                }
                for row in rows[:6]
            ]
            self._cg_cache.set(cache_key, result)
            return result
        except Exception:
            return cached or []

    def _get_coin_market_safe(self, coingecko_id: str, fallback_price: float) -> Dict[str, Any]:
        cache_key = f"coin_market:{coingecko_id}"
        cached = self._cg_cache.get(cache_key)

        url = f"{COINGECKO_BASE_URL}/coins/markets"
        params = {
            "vs_currency": "usd",
            "ids": coingecko_id,
            "sparkline": "false",
            "price_change_percentage": "24h",
        }

        try:
            resp = self.session.get(url, params=params, headers=self._cg_headers(), timeout=15)
            if resp.status_code == 429:
                return cached or {
                    "current_price": fallback_price,
                    "market_cap": None,
                    "total_volume": None,
                    "price_change_percentage_24h": None,
                }
            resp.raise_for_status()
            rows = resp.json()
            result = rows[0] if rows else {}
            if not result:
                result = {
                    "current_price": fallback_price,
                    "market_cap": None,
                    "total_volume": None,
                    "price_change_percentage_24h": None,
                }
            self._cg_cache.set(cache_key, result)
            return result
        except Exception:
            return cached or {
                "current_price": fallback_price,
                "market_cap": None,
                "total_volume": None,
                "price_change_percentage_24h": None,
            }

    def _get_binance_klines(self, symbol: str, interval: str, limit: int = 250) -> List[List[Any]]:
        url = f"{BINANCE_BASE_URL}/api/v3/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        resp = self.session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _build_dataframe(self, candles: List[List[Any]]) -> pd.DataFrame:
        df = pd.DataFrame(
            candles,
            columns=[
                "open_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_asset_volume",
                "number_of_trades",
                "taker_buy_base_asset_volume",
                "taker_buy_quote_asset_volume",
                "ignore",
            ],
        )
        for col in ["open", "high", "low", "close", "volume", "quote_asset_volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna().reset_index(drop=True)

    def _compute_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        ema_20 = close.ewm(span=20, adjust=False).mean()
        ema_50 = close.ewm(span=50, adjust=False).mean()

        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss.replace(0, math.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi = rsi.fillna(50)

        rsi_min = rsi.rolling(14).min()
        rsi_max = rsi.rolling(14).max()
        stoch_rsi = ((rsi - rsi_min) / (rsi_max - rsi_min).replace(0, math.nan) * 100).fillna(50)
        stoch_k = stoch_rsi.rolling(3).mean().fillna(50)
        stoch_d = stoch_k.rolling(3).mean().fillna(50)

        typical_price = (high + low + close) / 3
        money_flow = typical_price * volume
        positive_flow = []
        negative_flow = []

        for i in range(1, len(typical_price)):
            if typical_price.iloc[i] > typical_price.iloc[i - 1]:
                positive_flow.append(money_flow.iloc[i])
                negative_flow.append(0)
            else:
                positive_flow.append(0)
                negative_flow.append(money_flow.iloc[i])

        positive_mf = pd.Series([0] + positive_flow).rolling(14).sum()
        negative_mf = pd.Series([0] + negative_flow).rolling(14).sum()
        mfr = positive_mf / negative_mf.replace(0, math.nan)
        mfi = (100 - (100 / (1 + mfr))).fillna(50)

        ema_fast = close.ewm(span=12, adjust=False).mean()
        ema_slow = close.ewm(span=26, adjust=False).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=9, adjust=False).mean()
        macd_hist = macd - macd_signal

        volume_avg = volume.rolling(20).mean().fillna(volume.mean())
        volume_ratio = float(volume.iloc[-1] / volume_avg.iloc[-1]) if float(volume_avg.iloc[-1]) > 0 else 1.0
        volume_trend = "positive" if volume_ratio >= 1 else "neutral"
        trend = "bullish" if float(ema_20.iloc[-1]) > float(ema_50.iloc[-1]) else "bearish"

        return {
            "rsi": round(float(rsi.iloc[-1]), 2),
            "stochastic_rsi_k": round(float(stoch_k.iloc[-1]), 2),
            "stochastic_rsi_d": round(float(stoch_d.iloc[-1]), 2),
            "mfi": round(float(mfi.iloc[-1]), 2),
            "ema_20": round(float(ema_20.iloc[-1]), 6),
            "ema_50": round(float(ema_50.iloc[-1]), 6),
            "macd": round(float(macd.iloc[-1]), 6),
            "macd_signal": round(float(macd_signal.iloc[-1]), 6),
            "macd_hist": round(float(macd_hist.iloc[-1]), 6),
            "trend": trend,
            "volume_trend": volume_trend,
            "volume_ratio": round(volume_ratio, 2),
        }

    def _build_chart_series(self, df: pd.DataFrame) -> Dict[str, List[float]]:
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss.replace(0, math.nan)
        rsi = (100 - (100 / (1 + rs))).fillna(50)

        rsi_min = rsi.rolling(14).min()
        rsi_max = rsi.rolling(14).max()
        stoch_rsi = ((rsi - rsi_min) / (rsi_max - rsi_min).replace(0, math.nan) * 100).fillna(50)
        stoch_k = stoch_rsi.rolling(3).mean().fillna(50)
        stoch_d = stoch_k.rolling(3).mean().fillna(50)

        typical_price = (high + low + close) / 3
        money_flow = typical_price * volume

        positive_flow = [0]
        negative_flow = [0]
        for i in range(1, len(typical_price)):
            if typical_price.iloc[i] > typical_price.iloc[i - 1]:
                positive_flow.append(money_flow.iloc[i])
                negative_flow.append(0)
            else:
                positive_flow.append(0)
                negative_flow.append(money_flow.iloc[i])

        positive_mf = pd.Series(positive_flow).rolling(14).sum()
        negative_mf = pd.Series(negative_flow).rolling(14).sum()
        mfr = positive_mf / negative_mf.replace(0, math.nan)
        mfi = (100 - (100 / (1 + mfr))).fillna(50)

        return {
            "price": close.tail(60).round(6).tolist(),
            "rsi": rsi.tail(60).round(2).tolist(),
            "mfi": mfi.tail(60).round(2).tolist(),
            "stochastic_rsi_k": stoch_k.tail(60).round(2).tolist(),
            "stochastic_rsi_d": stoch_d.tail(60).round(2).tolist(),
            "volume": volume.tail(60).round(2).tolist(),
        }

    def _compute_levels(self, df: pd.DataFrame) -> Dict[str, float]:
        last_close = float(df["close"].iloc[-1])
        recent_high = float(df["high"].tail(30).max())
        recent_low = float(df["low"].tail(30).min())
        pivot = (recent_high + recent_low + last_close) / 3

        r1 = (2 * pivot) - recent_low
        s1 = (2 * pivot) - recent_high
        r2 = pivot + (recent_high - recent_low)
        s2 = pivot - (recent_high - recent_low)

        return {
            "pivot": round(pivot, 6),
            "resistance_1": round(r1, 6),
            "resistance_2": round(r2, 6),
            "support_1": round(s1, 6),
            "support_2": round(s2, 6),
        }

    def _compute_volatility(self, df: pd.DataFrame) -> Dict[str, Any]:
        high = df["high"]
        low = df["low"]
        close = df["close"]

        prev_close = close.shift(1)
        tr = pd.concat(
            [
                (high - low),
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)

        atr = tr.rolling(14).mean().fillna(tr.mean())
        atr_value = float(atr.iloc[-1])
        last_close = float(close.iloc[-1])
        atr_pct = (atr_value / last_close) * 100 if last_close > 0 else 0

        regime = "high" if atr_pct >= 3 else "medium" if atr_pct >= 1.2 else "low"

        return {
            "atr": round(atr_value, 6),
            "atr_pct": round(atr_pct, 2),
            "regime": regime,
        }

    def _simulate_orderflow(self, df: pd.DataFrame) -> Dict[str, Any]:
        recent = df.tail(30).copy()

        delta = recent["close"] - recent["open"]
        pressure = delta * recent["volume"]

        buy_pressure = float(pressure[pressure > 0].sum()) if not pressure[pressure > 0].empty else 0.0
        sell_pressure = abs(float(pressure[pressure < 0].sum())) if not pressure[pressure < 0].empty else 0.0
        total_pressure = buy_pressure + sell_pressure

        if total_pressure == 0:
            strength = 50
        else:
            dominance = abs(buy_pressure - sell_pressure) / total_pressure
            strength = int(50 + min(45, dominance * 100))

        last_volume = float(recent["volume"].iloc[-1])
        volume_avg = float(recent["volume"].rolling(10).mean().iloc[-1]) if len(recent) >= 10 else float(recent["volume"].mean())
        spike = volume_avg > 0 and last_volume >= volume_avg * 1.5

        upper_wick = float(recent["high"].iloc[-1] - max(recent["open"].iloc[-1], recent["close"].iloc[-1]))
        lower_wick = float(min(recent["open"].iloc[-1], recent["close"].iloc[-1]) - recent["low"].iloc[-1])
        candle_body = abs(float(recent["close"].iloc[-1] - recent["open"].iloc[-1]))

        if spike and candle_body > 0:
            if upper_wick > candle_body * 1.2:
                absorption = "high_sell_absorption"
            elif lower_wick > candle_body * 1.2:
                absorption = "high_buy_absorption"
            else:
                absorption = "low"
        else:
            absorption = "low"

        if buy_pressure > sell_pressure * 1.2:
            state = "aggressive_buying"
            imbalance = "buyers_in_control"
        elif sell_pressure > buy_pressure * 1.2:
            state = "aggressive_selling"
            imbalance = "sellers_in_control"
        else:
            state = "balanced"
            imbalance = "balanced_flow"

        return {
            "state": state,
            "imbalance": imbalance,
            "strength": max(40, min(95, strength)),
            "buy_pressure": round(buy_pressure, 2),
            "sell_pressure": round(sell_pressure, 2),
            "volume_spike": spike,
            "absorption": absorption,
        }

    def _build_signal(
        self,
        indicators: Dict[str, Any],
        indicator: str,
        orderflow: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, str, int]:
        trend = indicators["trend"]
        rsi = indicators["rsi"]
        stoch_k = indicators["stochastic_rsi_k"]
        stoch_d = indicators["stochastic_rsi_d"]
        mfi = indicators["mfi"]
        macd = indicators["macd"]
        macd_signal = indicators["macd_signal"]

        score = 0
        score += 25 if trend == "bullish" else -25

        if 50 <= rsi <= 70:
            score += 20
        elif rsi < 40:
            score -= 15
        elif rsi > 78:
            score -= 8

        if stoch_k > stoch_d and stoch_k < 80:
            score += 15
        elif stoch_k < stoch_d and stoch_k > 20:
            score -= 15

        if 50 <= mfi <= 75:
            score += 15
        elif mfi < 40:
            score -= 10
        elif mfi > 80:
            score -= 5

        score += 15 if macd > macd_signal else -15

        if indicator == "stochasticrsi":
            score += 10 if stoch_k > stoch_d else -10
        elif indicator == "rsi":
            score += 10 if rsi >= 50 else -10
        elif indicator == "mfi":
            score += 10 if mfi >= 50 else -10
        elif indicator == "macd":
            score += 10 if macd > macd_signal else -10
        elif indicator == "ema":
            score += 10 if trend == "bullish" else -10

        if orderflow:
            if orderflow["state"] == "aggressive_buying":
                score += 12
            elif orderflow["state"] == "aggressive_selling":
                score -= 12

            if orderflow["absorption"] == "high_buy_absorption":
                score += 6
            elif orderflow["absorption"] == "high_sell_absorption":
                score -= 6

        confidence = max(35, min(95, 50 + score))
        if confidence >= 72:
            return "buy", "bullish", int(confidence)
        if confidence <= 45:
            return "sell", "bearish", int(confidence)
        return "neutral", "mixed", int(confidence)

    def _build_confluence(self, results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        score = 0
        tf_biases = [results[tf]["bias"] for tf in self.MULTI_TIMEFRAMES]

        if all(b == "bullish" for b in tf_biases):
            score += 40
            alignment = "full_bullish_alignment"
        elif all(b == "bearish" for b in tf_biases):
            score += 40
            alignment = "full_bearish_alignment"
        else:
            alignment = "mixed_alignment"

        if results["1h"]["rsi"] >= 50:
            score += 10
        else:
            score -= 10

        if results["4h"]["trend"] == results["1d"]["trend"]:
            score += 20

        if results["15m"]["confidence"] >= 70:
            score += 10

        if results["1h"]["orderflow_state"] == "aggressive_buying":
            score += 10
        elif results["1h"]["orderflow_state"] == "aggressive_selling":
            score -= 10

        if results["4h"]["orderflow_state"] == results["1d"]["orderflow_state"]:
            score += 10

        confluence_score = max(20, min(100, 50 + score))

        dominant_bias = "mixed"
        bullish_count = sum(1 for b in tf_biases if b == "bullish")
        bearish_count = sum(1 for b in tf_biases if b == "bearish")
        if bullish_count > bearish_count:
            dominant_bias = "bullish"
        elif bearish_count > bullish_count:
            dominant_bias = "bearish"

        entry_quality = (
            "high"
            if confluence_score >= 80
            else "medium"
            if confluence_score >= 60
            else "low"
        )

        return {
            "score": confluence_score,
            "alignment": alignment,
            "dominant_bias": dominant_bias,
            "entry_quality": entry_quality,
            "timeframe_roles": {
                "15m": "entry_timing",
                "1h": "execution_bias",
                "4h": "market_structure",
                "1d": "macro_trend",
            },
        }

    def _build_premium_payload(
        self,
        token: str,
        interval: str,
        indicators: Dict[str, Any],
        orderflow: Dict[str, Any],
        levels: Dict[str, float],
        multi_timeframe: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        tf_data = multi_timeframe["timeframes"] if multi_timeframe else {}

        def bias_label(tf: str) -> str:
            item = tf_data.get(tf, {})
            return item.get("bias", "unknown")

        rsi_state = (
            "bullish"
            if indicators["rsi"] >= 55
            else "bearish"
            if indicators["rsi"] <= 45
            else "neutral"
        )
        mfi_state = (
            "supported"
            if indicators["mfi"] >= 55
            else "weak"
            if indicators["mfi"] <= 45
            else "neutral"
        )
        macd_state = "positive_cross" if indicators["macd"] > indicators["macd_signal"] else "negative_cross"
        volume_state = "expansion" if indicators["volume_ratio"] >= 1.2 else "normal"

        ai_context = (
            f"{token} {interval}: "
            f"trend={indicators['trend']}, "
            f"rsi={indicators['rsi']}, "
            f"mfi={indicators['mfi']}, "
            f"orderflow={orderflow['state']}, "
            f"confluence={multi_timeframe['confluence']['score'] if multi_timeframe else 'n/a'}."
        )

        return {
            "bias_15m": bias_label("15m"),
            "bias_1h": bias_label("1h"),
            "bias_4h": bias_label("4h"),
            "bias_1d": bias_label("1d"),
            "indicator_breakdown": {
                "rsi_state": rsi_state,
                "mfi_state": mfi_state,
                "macd_regime": macd_state,
                "volume_quality": volume_state,
            },
            "premium_ai_context": ai_context,
            "liquidity_map": {
                "pivot": levels["pivot"],
                "resistance_cluster": [levels["resistance_1"], levels["resistance_2"]],
                "support_cluster": [levels["support_1"], levels["support_2"]],
            },
        }

    def _build_vip_payload(
        self,
        token: str,
        interval: str,
        indicators: Dict[str, Any],
        orderflow: Dict[str, Any],
        levels: Dict[str, float],
        signal: str,
        bias: str,
        confidence: int,
        multi_timeframe: Optional[Dict[str, Any]],
        volatility: Dict[str, Any],
    ) -> Dict[str, Any]:
        confluence_score = multi_timeframe["confluence"]["score"] if multi_timeframe else confidence
        vip_score = int(round((confidence * 0.45) + (confluence_score * 0.40) + (orderflow["strength"] * 0.15)))
        vip_score = max(40, min(98, vip_score))

        if vip_score >= 82:
            execution_mode = "aggressive_selective"
        elif vip_score >= 68:
            execution_mode = "selective"
        else:
            execution_mode = "defensive"

        risk_profile = (
            "controlled"
            if volatility["regime"] == "low"
            else "adaptive"
            if volatility["regime"] == "medium"
            else "high_volatility"
        )

        bull_scenario = (
            f"Maintien au-dessus de {levels['pivot']} puis attaque de {levels['resistance_1']} "
            f"avec orderflow {orderflow['state']}."
        )
        bear_scenario = (
            f"Perte de {levels['pivot']} puis pression vers {levels['support_1']} "
            f"si les vendeurs gardent le contrôle."
        )
        neutral_scenario = (
            f"Compression entre {levels['support_1']} et {levels['resistance_1']}, "
            f"attendre un breakout confirmé par volume."
        )

        desk_notes = (
            f"{token} {interval} | signal={signal} | bias={bias} | "
            f"confluence={confluence_score} | orderflow={orderflow['state']} | "
            f"volatility={volatility['regime']}."
        )

        telegram_ready = vip_score >= 80 and confluence_score >= 75 and signal == "buy"

        return {
            "score": vip_score,
            "execution_mode": execution_mode,
            "risk_profile": risk_profile,
            "bullish_scenario": bull_scenario,
            "bearish_scenario": bear_scenario,
            "neutral_scenario": neutral_scenario,
            "desk_notes": desk_notes,
            "telegram_alert_candidate": telegram_ready,
        }

    def _record_and_build_setup_replay(
        self,
        token: str,
        interval: str,
        signal: str,
        bias: str,
        confidence: int,
        current_price: float,
        orderflow: Dict[str, Any],
        multi_timeframe: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        confluence_score = multi_timeframe["confluence"]["score"] if multi_timeframe else None

        simulated_outcome_pct: Optional[float]
        if signal == "buy" and bias == "bullish":
            simulated_outcome_pct = round((confidence - 50) / 10, 2)
        elif signal == "sell" and bias == "bearish":
            simulated_outcome_pct = round((confidence - 50) / 12, 2)
        else:
            simulated_outcome_pct = round(-abs(50 - confidence) / 20, 2)

        row = {
            "timestamp": int(time.time()),
            "token": token,
            "interval": interval,
            "signal": signal,
            "bias": bias,
            "confidence": confidence,
            "price": round(current_price, 6),
            "orderflow_state": orderflow["state"],
            "orderflow_strength": orderflow["strength"],
            "confluence_score": confluence_score,
            "simulated_outcome_pct": simulated_outcome_pct,
        }

        try:
            self.replay_store.record_setup(row)
        except Exception:
            pass

        try:
            summary = self.replay_store.summarize(token=token, interval=interval)
        except Exception:
            summary = {
                "count": 0,
                "winrate": None,
                "avg_confidence": None,
                "last_setups": [],
                "best_bias": None,
            }

        return summary

    def build_premium_insight(self, token: str, interval: str, indicator: str, insight_type: Optional[str] = None) -> Dict[str, Any]:
        analysis = self.analyze(token=token, interval=interval, indicator=indicator, include_multi_tf=True)
        data = analysis.to_dict()

        return {
            "type": insight_type or "premium-overview",
            "premium_data": {
                "rsi": data["indicators"]["rsi"],
                "mfi": data["indicators"]["mfi"],
                "trend": data["summary_context"]["trend"],
                "orderflow": data["orderflow"],
                "multi_timeframe": data["multi_timeframe"],
                "premium": data["premium"],
                "setup_replay": data["setup_replay"],
            },
        }

    def build_vip_insight(self, token: str, interval: str, indicator: str, insight_type: Optional[str] = None) -> Dict[str, Any]:
        analysis = self.analyze(token=token, interval=interval, indicator=indicator, include_multi_tf=True)
        data = analysis.to_dict()

        return {
            "type": insight_type or "vip-overview",
            "vip_data": {
                "score": data["vip"]["score"] if data.get("vip") else data["confidence"],
                "bias": data["bias"],
                "trend": data["summary_context"]["trend"],
                "orderflow": data["orderflow"],
                "multi_timeframe": data["multi_timeframe"],
                "vip": data["vip"],
                "setup_replay": data["setup_replay"],
            },
        }

    def _cg_headers(self) -> Dict[str, str]:
        headers = {"accept": "application/json"}
        if self.coingecko_api_key:
            headers["x-cg-demo-api-key"] = self.coingecko_api_key
        return headers