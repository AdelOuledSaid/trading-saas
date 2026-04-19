from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass
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

    _cg_cache = SimpleTTLCache(ttl_seconds=90)

    def __init__(self) -> None:
        self.session = requests.Session()
        self.coingecko_api_key = os.getenv("COINGECKO_API_KEY", "").strip()

    def get_available_tokens(self) -> List[Dict[str, str]]:
        return [
            {"token": token, "coingecko_id": meta["coingecko_id"], "symbol": meta["binance_symbol"]}
            for token, meta in self.TOKEN_MAP.items()
        ]

    def analyze(self, token: str, interval: str, indicator: str) -> AnalysisResult:
        token = (token or "BTC").upper().strip()
        interval = (interval or "1h").lower().strip()
        indicator = (indicator or "stochasticrsi").lower().strip()

        if token not in self.TOKEN_MAP:
            token = "BTC"
        if interval not in self.SUPPORTED_INTERVALS:
            interval = "1h"
        if indicator not in self.SUPPORTED_INDICATORS:
            indicator = "stochasticrsi"

        meta = self.TOKEN_MAP[token]

        candles = self._get_binance_klines(meta["binance_symbol"], interval=interval, limit=250)
        df = self._build_dataframe(candles)

        indicators = self._compute_indicators(df)
        levels = self._compute_levels(df)
        signal, bias, confidence = self._build_signal(indicators, indicator)

        # CoinGecko devient optionnel, pas bloquant
        cg_data = self._get_coin_market_safe(meta["coingecko_id"], fallback_price=float(df["close"].iloc[-1]))
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
        }

        return AnalysisResult(
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
        )

    def get_watchlist_safe(self) -> List[Dict[str, Any]]:
        cache_key = "watchlist"
        cached = self._cg_cache.get(cache_key)
        if cached is not None:
            return cached

        ids = ",".join([
            self.TOKEN_MAP["BTC"]["coingecko_id"],
            self.TOKEN_MAP["ETH"]["coingecko_id"],
            self.TOKEN_MAP["XRP"]["coingecko_id"],
            self.TOKEN_MAP["SOL"]["coingecko_id"],
        ])
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
                "open_time", "open", "high", "low", "close", "volume", "close_time",
                "quote_asset_volume", "number_of_trades", "taker_buy_base_asset_volume",
                "taker_buy_quote_asset_volume", "ignore",
            ],
        )
        for col in ["open", "high", "low", "close", "volume"]:
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

        volume_avg = volume.rolling(20).mean().fillna(volume.mean())
        volume_trend = "positive" if float(volume.iloc[-1]) >= float(volume_avg.iloc[-1]) else "neutral"
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
            "trend": trend,
            "volume_trend": volume_trend,
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

    def _build_signal(self, indicators: Dict[str, Any], indicator: str) -> tuple[str, str, int]:
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

        if stoch_k > stoch_d and stoch_k < 80:
            score += 15
        elif stoch_k < stoch_d and stoch_k > 20:
            score -= 15

        if 50 <= mfi <= 75:
            score += 15
        elif mfi < 40:
            score -= 10

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

        confidence = max(35, min(92, 50 + score))
        if confidence >= 72:
            return "buy", "bullish", int(confidence)
        if confidence <= 45:
            return "sell", "bearish", int(confidence)
        return "neutral", "mixed", int(confidence)

    def _cg_headers(self) -> Dict[str, str]:
        headers = {"accept": "application/json"}
        if self.coingecko_api_key:
            headers["x-cg-demo-api-key"] = self.coingecko_api_key
        return headers