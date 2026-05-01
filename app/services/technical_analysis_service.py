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
    ai_advanced_analysis: Optional[Dict[str, Any]] = None

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
            "ai_advanced_analysis": self.ai_advanced_analysis,
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
        clipped = rows[-self.limit:]
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
        "ADA": {"coingecko_id": "cardano", "binance_symbol": "ADAUSDT"},
        "AVAX": {"coingecko_id": "avalanche-2", "binance_symbol": "AVAXUSDT"},
        "LINK": {"coingecko_id": "chainlink", "binance_symbol": "LINKUSDT"},
        "MATIC": {"coingecko_id": "matic-network", "binance_symbol": "MATICUSDT"},
        "TRX": {"coingecko_id": "tron", "binance_symbol": "TRXUSDT"},
        "LTC": {"coingecko_id": "litecoin", "binance_symbol": "LTCUSDT"},
        "DOT": {"coingecko_id": "polkadot", "binance_symbol": "DOTUSDT"},
        "UNI": {"coingecko_id": "uniswap", "binance_symbol": "UNIUSDT"},
        "ATOM": {"coingecko_id": "cosmos", "binance_symbol": "ATOMUSDT"},
    }

    SUPPORTED_INTERVALS = {"15m", "1h", "4h", "1d"}
    SUPPORTED_INDICATORS = {"rsi", "stochasticrsi", "mfi", "ema", "macd"}
    MULTI_TIMEFRAMES = ("15m", "1h", "4h", "1d")

    _cg_cache = SimpleTTLCache(ttl_seconds=90)
    _analysis_cache = SimpleTTLCache(ttl_seconds=120)

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
        candles = self._get_binance_klines(meta["binance_symbol"], interval=interval, limit=120)
        df = self._build_dataframe(candles)

        indicators = self._compute_indicators(df)
        levels = self._compute_levels(df)
        chart_series = self._build_chart_series(df)
        volatility = self._compute_volatility(df)
        market_structure = self._analyze_market_structure(df)
        orderflow = self._simulate_orderflow(df)
        signal, bias, confidence = self._build_signal(indicators, indicator, orderflow)

        cg_data = self._get_coin_market_safe(
            meta["coingecko_id"],
            fallback_price=float(df["close"].iloc[-1]),
        )
        watchlist = self.get_watchlist_safe()
        trending = self.get_trending_safe()
        multi_timeframe = self.multi_timeframe_analysis(token=token, primary_indicator=indicator) if include_multi_tf else None

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
            "delta_pressure": orderflow["delta_pressure"],
            "market_structure": market_structure["structure"],
            "momentum_regime": market_structure["momentum"],
            "volatility": volatility,
        }

        premium = self._build_premium_payload(
            token=token,
            interval=interval,
            indicators=indicators,
            orderflow=orderflow,
            levels=levels,
            multi_timeframe=multi_timeframe,
            market_structure=market_structure,
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
            market_structure=market_structure,
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

        ai_advanced_analysis = self._build_ai_advanced_analysis(
            token=token,
            interval=interval,
            current_price=float(df["close"].iloc[-1]),
            signal=signal,
            bias=bias,
            confidence=confidence,
            indicators=indicators,
            levels=levels,
            orderflow=orderflow,
            market_structure=market_structure,
            multi_timeframe=multi_timeframe,
            volatility=volatility,
            setup_replay=setup_replay,
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
            ai_advanced_analysis=ai_advanced_analysis,
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
            structure = self._analyze_market_structure(df)
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
                "delta_pressure": orderflow["delta_pressure"],
                "market_structure": structure["structure"],
                "momentum": structure["momentum"],
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

        watch_tokens = ["BTC", "ETH", "SOL", "XRP", "BNB", "ADA"]
        ids = ",".join([self.TOKEN_MAP[t]["coingecko_id"] for t in watch_tokens if t in self.TOKEN_MAP])

        url = f"{COINGECKO_BASE_URL}/coins/markets"
        params = {
            "vs_currency": "usd",
            "ids": ids,
            "price_change_percentage": "24h",
            "sparkline": "false",
        }

        try:
            resp = self.session.get(url, params=params, headers=self._cg_headers(), timeout=6)
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
            "per_page": 8,
            "page": 1,
            "sparkline": "false",
            "price_change_percentage": "24h",
        }

        try:
            resp = self.session.get(url, params=params, headers=self._cg_headers(), timeout=6)
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
                for row in rows[:8]
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
            resp = self.session.get(url, params=params, headers=self._cg_headers(), timeout=6)
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
        """
        Return OHLCV candles in Binance kline format.

        Binance can return HTTP 451 on some cloud providers/regions, including
        Render. In that case we automatically fall back to OKX public market
        candles. The returned rows keep the same shape expected by
        _build_dataframe(), so the rest of the analysis remains unchanged.

        NOTE:
        - Price candles from OKX are real market data.
        - quote_asset_volume, number_of_trades and taker buy fields are not
          provided by OKX candles, so they are approximated with neutral values.
        """
        url = f"{BINANCE_BASE_URL}/api/v3/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}

        try:
            resp = self.session.get(url, params=params, timeout=6)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return self._get_okx_klines(symbol=symbol, interval=interval, limit=limit)

    def _get_okx_klines(self, symbol: str, interval: str, limit: int = 250) -> List[List[Any]]:
        """
        Fetch real OHLCV candles from OKX and convert them to Binance kline shape.

        OKX endpoint:
        https://www.okx.com/api/v5/market/candles

        OKX response candle format:
        [ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm]

        Binance-like output expected by _build_dataframe:
        [
            open_time, open, high, low, close, volume, close_time,
            quote_asset_volume, number_of_trades,
            taker_buy_base_asset_volume, taker_buy_quote_asset_volume, ignore
        ]
        """
        okx_symbol = symbol.replace("USDT", "-USDT")

        interval_map = {
            "15m": "15m",
            "1h": "1H",
            "4h": "4H",
            "1d": "1D",
        }

        url = "https://www.okx.com/api/v5/market/candles"
        params = {
            "instId": okx_symbol,
            "bar": interval_map.get(interval, "1H"),
            "limit": str(limit),
        }

        resp = self.session.get(url, params=params, timeout=8)
        resp.raise_for_status()
        payload = resp.json()

        if str(payload.get("code", "0")) != "0":
            raise RuntimeError(f"OKX API error: {payload}")

        data = payload.get("data", [])
        if not data:
            raise RuntimeError("OKX returned empty candles")

        rows: List[List[Any]] = []

        # OKX returns candles newest first. Pandas indicators need oldest first.
        for candle in reversed(data):
            ts = int(candle[0])
            open_ = candle[1]
            high = candle[2]
            low = candle[3]
            close = candle[4]
            volume = candle[5]
            quote_volume = candle[7] if len(candle) > 7 else "0"

            close_time = ts
            number_of_trades = 0

            # OKX candles do not provide taker-buy split. Use neutral 50/50
            # approximation so orderflow does not break.
            try:
                taker_buy_base = str(float(volume) * 0.5)
            except Exception:
                taker_buy_base = "0"

            try:
                taker_buy_quote = str(float(quote_volume) * 0.5)
            except Exception:
                taker_buy_quote = "0"

            rows.append([
                ts,
                open_,
                high,
                low,
                close,
                volume,
                close_time,
                quote_volume,
                number_of_trades,
                taker_buy_base,
                taker_buy_quote,
                0,
            ])

        return rows

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
        for col in [
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_asset_volume",
            "number_of_trades",
            "taker_buy_base_asset_volume",
            "taker_buy_quote_asset_volume",
        ]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna().reset_index(drop=True)

    def _compute_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        ema_20 = close.ewm(span=20, adjust=False).mean()
        ema_50 = close.ewm(span=50, adjust=False).mean()
        ema_200 = close.ewm(span=200, adjust=False).mean()

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

        ema_fast = close.ewm(span=12, adjust=False).mean()
        ema_slow = close.ewm(span=26, adjust=False).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=9, adjust=False).mean()
        macd_hist = macd - macd_signal

        volume_avg = volume.rolling(20).mean().fillna(volume.mean())
        volume_ratio = float(volume.iloc[-1] / volume_avg.iloc[-1]) if float(volume_avg.iloc[-1]) > 0 else 1.0
        volume_trend = "positive" if volume_ratio >= 1.05 else "neutral"
        trend = "bullish" if float(ema_20.iloc[-1]) > float(ema_50.iloc[-1]) else "bearish"
        trend_strength = self._clamp(abs(float(ema_20.iloc[-1] - ema_50.iloc[-1])) / max(float(close.iloc[-1]), 1e-9) * 1000, 0, 100)

        return {
            "rsi": round(float(rsi.iloc[-1]), 2),
            "stochastic_rsi_k": round(float(stoch_k.iloc[-1]), 2),
            "stochastic_rsi_d": round(float(stoch_d.iloc[-1]), 2),
            "mfi": round(float(mfi.iloc[-1]), 2),
            "ema_20": round(float(ema_20.iloc[-1]), 6),
            "ema_50": round(float(ema_50.iloc[-1]), 6),
            "ema_200": round(float(ema_200.iloc[-1]), 6),
            "macd": round(float(macd.iloc[-1]), 6),
            "macd_signal": round(float(macd_signal.iloc[-1]), 6),
            "macd_hist": round(float(macd_hist.iloc[-1]), 6),
            "trend": trend,
            "trend_strength": round(float(trend_strength), 2),
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
        tr = pd.concat([
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)

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

    def _analyze_market_structure(self, df: pd.DataFrame) -> Dict[str, Any]:
        recent_20 = df.tail(20)
        recent_50 = df.tail(50)
        last_close = float(df["close"].iloc[-1])

        hh_20 = float(recent_20["high"].max())
        ll_20 = float(recent_20["low"].min())
        hh_50 = float(recent_50["high"].max())
        ll_50 = float(recent_50["low"].min())

        ema20 = float(df["close"].ewm(span=20, adjust=False).mean().iloc[-1])
        ema50 = float(df["close"].ewm(span=50, adjust=False).mean().iloc[-1])

        recent_highs = recent_20["high"].tail(5).mean()
        earlier_highs = recent_20["high"].head(5).mean()
        recent_lows = recent_20["low"].tail(5).mean()
        earlier_lows = recent_20["low"].head(5).mean()

        if recent_highs > earlier_highs and recent_lows > earlier_lows and ema20 > ema50:
            structure = "bullish_trend_structure"
        elif recent_highs < earlier_highs and recent_lows < earlier_lows and ema20 < ema50:
            structure = "bearish_trend_structure"
        elif last_close > (hh_20 + ll_20) / 2:
            structure = "bullish_range_structure"
        elif last_close < (hh_20 + ll_20) / 2:
            structure = "bearish_range_structure"
        else:
            structure = "neutral_compression"

        impulse_pct = self._pct(hh_20 - ll_20, ll_20 if ll_20 > 0 else last_close)
        if structure.startswith("bullish") and impulse_pct >= 4:
            momentum = "strong_bullish_momentum"
        elif structure.startswith("bearish") and impulse_pct >= 4:
            momentum = "strong_bearish_momentum"
        elif structure.startswith("bullish"):
            momentum = "building_bullish_momentum"
        elif structure.startswith("bearish"):
            momentum = "building_bearish_momentum"
        else:
            momentum = "balanced_momentum"

        location_20 = self._safe_div(last_close - ll_20, hh_20 - ll_20)
        structure_score = 50
        if structure.startswith("bullish"):
            structure_score += 20
        elif structure.startswith("bearish"):
            structure_score -= 20
        structure_score += int((location_20 - 0.5) * 30)
        structure_score = int(self._clamp(structure_score, 5, 95))

        return {
            "structure": structure,
            "momentum": momentum,
            "range_high_20": round(hh_20, 6),
            "range_low_20": round(ll_20, 6),
            "range_high_50": round(hh_50, 6),
            "range_low_50": round(ll_50, 6),
            "location_in_range_20": round(location_20, 3),
            "score": structure_score,
        }

    def _simulate_orderflow(self, df: pd.DataFrame) -> Dict[str, Any]:
        recent = df.tail(30).copy()
        last = recent.iloc[-1]

        delta = recent["close"] - recent["open"]
        pressure = delta * recent["volume"]
        buy_pressure = float(pressure[pressure > 0].sum()) if not pressure[pressure > 0].empty else 0.0
        sell_pressure = abs(float(pressure[pressure < 0].sum())) if not pressure[pressure < 0].empty else 0.0
        total_pressure = buy_pressure + sell_pressure

        if total_pressure == 0:
            dominance = 0.0
            strength = 50
        else:
            dominance = abs(buy_pressure - sell_pressure) / total_pressure
            strength = int(50 + min(45, dominance * 100))

        candle_range = max(float(last["high"] - last["low"]), 1e-9)
        candle_body = abs(float(last["close"] - last["open"]))
        upper_wick = float(last["high"] - max(last["open"], last["close"]))
        lower_wick = float(min(last["open"], last["close"]) - last["low"])
        body_ratio = candle_body / candle_range
        upper_wick_ratio = upper_wick / candle_range
        lower_wick_ratio = lower_wick / candle_range
        close_position = self._safe_div(float(last["close"] - last["low"]), candle_range)

        last5_vol = float(recent["volume"].tail(5).mean())
        prev5_vol = float(recent["volume"].tail(10).head(5).mean()) if len(recent) >= 10 else float(recent["volume"].mean())
        volume_acceleration = self._safe_div(last5_vol, prev5_vol if prev5_vol > 0 else 1.0)
        volume_spike = volume_acceleration >= 1.3

        last5_qav = float(recent["quote_asset_volume"].tail(5).sum())
        last5_taker_buy_qav = float(recent["taker_buy_quote_asset_volume"].tail(5).sum())
        taker_buy_ratio = self._safe_div(last5_taker_buy_qav, last5_qav if last5_qav > 0 else 1.0)
        taker_sell_ratio = max(0.0, 1.0 - taker_buy_ratio)

        green_body_pressure = float(((recent["close"] - recent["open"]).clip(lower=0) * recent["quote_asset_volume"]).sum())
        red_body_pressure = float(((-(recent["close"] - recent["open"]).clip(upper=0)) * recent["quote_asset_volume"]).sum())
        body_total = green_body_pressure + red_body_pressure
        body_buy_ratio = self._safe_div(green_body_pressure, body_total if body_total > 0 else 1.0)

        buyer_aggression = self._clamp((taker_buy_ratio * 45) + (body_buy_ratio * 35) + (close_position * 20), 0, 100)
        seller_aggression = self._clamp(100 - buyer_aggression, 0, 100)

        absorption_score = 0
        if volume_spike and upper_wick_ratio >= 0.32 and close_position <= 0.45:
            absorption = "high_sell_absorption"
            absorption_score = -2
        elif volume_spike and lower_wick_ratio >= 0.32 and close_position >= 0.55:
            absorption = "high_buy_absorption"
            absorption_score = 2
        elif volume_spike and (upper_wick_ratio >= 0.22 or lower_wick_ratio >= 0.22):
            absorption = "moderate_absorption"
            absorption_score = 1 if lower_wick_ratio > upper_wick_ratio else -1
        else:
            absorption = "low"

        if taker_buy_ratio >= 0.57 and buyer_aggression >= 58:
            delta_pressure = "buyer_pressure"
        elif taker_buy_ratio <= 0.43 and seller_aggression >= 58:
            delta_pressure = "seller_pressure"
        else:
            delta_pressure = "balanced_pressure"

        if close_position >= 0.75 and body_ratio >= 0.45:
            imbalance_zone = "upper_imbalance"
        elif close_position <= 0.25 and body_ratio >= 0.45:
            imbalance_zone = "lower_imbalance"
        elif body_ratio <= 0.22 and (upper_wick_ratio >= 0.25 or lower_wick_ratio >= 0.25):
            imbalance_zone = "wick_rejection_zone"
        else:
            imbalance_zone = "inside_balance"

        recent_returns = recent["close"].pct_change().tail(4).fillna(0)
        one_sided_run = (recent_returns.gt(0).sum() >= 3) or (recent_returns.lt(0).sum() >= 3)
        exhaustion = bool(
            volume_spike
            and body_ratio <= 0.25
            and one_sided_run
            and (upper_wick_ratio >= 0.25 or lower_wick_ratio >= 0.25)
        )

        if delta_pressure == "buyer_pressure" and buy_pressure > sell_pressure * 1.15:
            state = "aggressive_buying"
            imbalance = "buyers_in_control"
        elif delta_pressure == "seller_pressure" and sell_pressure > buy_pressure * 1.15:
            state = "aggressive_selling"
            imbalance = "sellers_in_control"
        elif absorption.startswith("high_"):
            state = "absorption_active"
            imbalance = "reversal_interest"
        else:
            state = "balanced"
            imbalance = "balanced_flow"

        if exhaustion and delta_pressure == "buyer_pressure":
            dominant_signal = "bullish_exhaustion"
        elif exhaustion and delta_pressure == "seller_pressure":
            dominant_signal = "bearish_exhaustion"
        elif absorption == "high_buy_absorption":
            dominant_signal = "buyer_absorption"
        elif absorption == "high_sell_absorption":
            dominant_signal = "seller_absorption"
        elif buyer_aggression >= 60:
            dominant_signal = "buyer_aggression"
        elif seller_aggression >= 60:
            dominant_signal = "seller_aggression"
        else:
            dominant_signal = "balanced_orderflow"

        return {
            "state": state,
            "imbalance": imbalance,
            "strength": int(self._clamp(strength, 40, 95)),
            "buy_pressure": round(buy_pressure, 2),
            "sell_pressure": round(sell_pressure, 2),
            "volume_spike": volume_spike,
            "absorption": absorption,
            "buyer_aggression": round(buyer_aggression, 2),
            "seller_aggression": round(seller_aggression, 2),
            "body_ratio": round(body_ratio, 3),
            "upper_wick_ratio": round(upper_wick_ratio, 3),
            "lower_wick_ratio": round(lower_wick_ratio, 3),
            "close_position": round(close_position, 3),
            "volume_acceleration": round(volume_acceleration, 2),
            "absorption_score": absorption_score,
            "delta_pressure": delta_pressure,
            "imbalance_zone": imbalance_zone,
            "dominant_signal": dominant_signal,
            "exhaustion": exhaustion,
            "taker_buy_ratio": round(taker_buy_ratio, 3),
            "taker_sell_ratio": round(taker_sell_ratio, 3),
            "candle_range": round(candle_range, 6),
            "candle_body": round(candle_body, 6),
        }

    def _build_signal(self, indicators: Dict[str, Any], indicator: str, orderflow: Optional[Dict[str, Any]] = None) -> tuple[str, str, int]:
        trend = indicators["trend"]
        rsi = indicators["rsi"]
        stoch_k = indicators["stochastic_rsi_k"]
        stoch_d = indicators["stochastic_rsi_d"]
        mfi = indicators["mfi"]
        macd = indicators["macd"]
        macd_signal = indicators["macd_signal"]
        macd_hist = indicators["macd_hist"]

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
        score += 5 if macd_hist > 0 else -5

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
                score += 7
            elif orderflow["absorption"] == "high_sell_absorption":
                score -= 7

            if orderflow["dominant_signal"] == "buyer_aggression":
                score += 10
            elif orderflow["dominant_signal"] == "seller_aggression":
                score -= 10
            elif orderflow["dominant_signal"] == "bullish_exhaustion":
                score -= 6
            elif orderflow["dominant_signal"] == "bearish_exhaustion":
                score += 6

        confidence = int(self._clamp(50 + score, 35, 95))
        if confidence >= 72:
            return "buy", "bullish", confidence
        if confidence <= 45:
            return "sell", "bearish", confidence
        return "neutral", "mixed", confidence

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

        if results["4h"]["market_structure"].startswith("bullish") and results["1d"]["market_structure"].startswith("bullish"):
            score += 10
        elif results["4h"]["market_structure"].startswith("bearish") and results["1d"]["market_structure"].startswith("bearish"):
            score += 10

        confluence_score = int(self._clamp(50 + score, 20, 100))

        bullish_count = sum(1 for b in tf_biases if b == "bullish")
        bearish_count = sum(1 for b in tf_biases if b == "bearish")
        dominant_bias = "mixed"
        if bullish_count > bearish_count:
            dominant_bias = "bullish"
        elif bearish_count > bullish_count:
            dominant_bias = "bearish"

        entry_quality = "high" if confluence_score >= 80 else "medium" if confluence_score >= 60 else "low"

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

    def _build_ai_advanced_analysis(
        self,
        token: str,
        interval: str,
        current_price: float,
        signal: str,
        bias: str,
        confidence: int,
        indicators: Dict[str, Any],
        levels: Dict[str, float],
        orderflow: Dict[str, Any],
        market_structure: Dict[str, Any],
        multi_timeframe: Optional[Dict[str, Any]],
        volatility: Dict[str, Any],
        setup_replay: Dict[str, Any],
    ) -> Dict[str, Any]:
        mtf = multi_timeframe or {"timeframes": {}, "confluence": {}}
        confluence = mtf.get("confluence", {})
        tf = mtf.get("timeframes", {})

        market_structure_text = (
            f"{market_structure['structure']} | location={market_structure['location_in_range_20']} | "
            f"score={market_structure['score']}"
        )

        if indicators["macd"] > indicators["macd_signal"] and indicators["rsi"] >= 55 and indicators["mfi"] >= 55:
            momentum = "impulsive_bullish_momentum"
        elif indicators["macd"] < indicators["macd_signal"] and indicators["rsi"] <= 45 and indicators["mfi"] <= 45:
            momentum = "impulsive_bearish_momentum"
        elif indicators["rsi"] > 50 and indicators["macd_hist"] > 0:
            momentum = "constructive_bullish_momentum"
        elif indicators["rsi"] < 50 and indicators["macd_hist"] < 0:
            momentum = "constructive_bearish_momentum"
        else:
            momentum = "neutral_momentum"

        simulated_orderflow = {
            "state": orderflow["state"],
            "dominant_signal": orderflow["dominant_signal"],
            "buyer_aggression": orderflow["buyer_aggression"],
            "seller_aggression": orderflow["seller_aggression"],
            "absorption": orderflow["absorption"],
            "exhaustion": orderflow["exhaustion"],
            "delta_pressure": orderflow["delta_pressure"],
            "imbalance_zone": orderflow["imbalance_zone"],
            "close_position": orderflow["close_position"],
            "body_ratio": orderflow["body_ratio"],
            "volume_acceleration": orderflow["volume_acceleration"],
            "interpretation": self._build_orderflow_commentary(orderflow),
        }

        multi_timeframe_context = {
            "15m": tf.get("15m"),
            "1h": tf.get("1h"),
            "4h": tf.get("4h"),
            "1d": tf.get("1d"),
            "confluence_score": confluence.get("score"),
            "alignment": confluence.get("alignment"),
            "dominant_bias": confluence.get("dominant_bias"),
            "entry_quality": confluence.get("entry_quality"),
        }

        bull_scenario = {
            "title": "bull continuation",
            "trigger": (
                f"Hold above pivot {levels['pivot']} and keep acceptance above support/pivot rotation with "
                f"buyer pressure or buy absorption."
            ),
            "confirmation": (
                f"Break and sustain above {levels['resistance_1']} with volume_acceleration >= 1.20 and "
                f"close_position > 0.65."
            ),
            "targets": [levels["resistance_1"], levels["resistance_2"]],
            "orderflow_requirement": "buyer_aggression or buyer_absorption must remain dominant",
        }

        bear_scenario = {
            "title": "bear continuation",
            "trigger": (
                f"Lose pivot {levels['pivot']} and fail reclaim while seller pressure or sell absorption remains active."
            ),
            "confirmation": (
                f"Acceptance below {levels['support_1']} with seller_aggression rising and close_position < 0.35."
            ),
            "targets": [levels["support_1"], levels["support_2"]],
            "orderflow_requirement": "seller_aggression or seller_absorption must remain dominant",
        }

        neutral_scenario = {
            "title": "range / wait",
            "trigger": (
                f"Price remains between {levels['support_1']} and {levels['resistance_1']} with balanced pressure."
            ),
            "confirmation": "Wait for a breakout with body expansion and synchronous delta pressure.",
            "targets": [levels["pivot"]],
            "orderflow_requirement": "balanced_pressure or wick rejection without follow-through",
        }

        invalidation = self._build_invalidation_text(bias=bias, levels=levels, orderflow=orderflow)
        execution_note = self._build_execution_note(
            token=token,
            interval=interval,
            signal=signal,
            bias=bias,
            confidence=confidence,
            indicators=indicators,
            orderflow=orderflow,
            confluence=confluence,
            volatility=volatility,
            setup_replay=setup_replay,
        )

        return {
            "market_structure": market_structure_text,
            "momentum": momentum,
            "simulated_orderflow": simulated_orderflow,
            "multi_timeframe_context": multi_timeframe_context,
            "bull_scenario": bull_scenario,
            "bear_scenario": bear_scenario,
            "neutral_scenario": neutral_scenario,
            "invalidation": invalidation,
            "execution_note": execution_note,
            "trade_plan": {
                "signal": signal,
                "bias": bias,
                "confidence": confidence,
                "current_price": round(current_price, 6),
                "volatility_regime": volatility["regime"],
                "confluence_score": confluence.get("score"),
            },
        }

    def _build_orderflow_commentary(self, orderflow: Dict[str, Any]) -> str:
        if orderflow["dominant_signal"] == "buyer_aggression":
            return "buyers are lifting offers with closing strength and supportive candle anatomy"
        if orderflow["dominant_signal"] == "seller_aggression":
            return "sellers are pressing bids with weak closes and downside acceptance"
        if orderflow["dominant_signal"] == "buyer_absorption":
            return "dip selling is being absorbed; lower wick acceptance suggests responsive buyers"
        if orderflow["dominant_signal"] == "seller_absorption":
            return "upside auction is being absorbed; upper wick rejection suggests responsive sellers"
        if orderflow["dominant_signal"] == "bullish_exhaustion":
            return "buyers still control delta but candle efficiency is fading; chase entries are risky"
        if orderflow["dominant_signal"] == "bearish_exhaustion":
            return "sellers still control delta but downside efficiency is fading; late shorts are risky"
        return "flow is balanced and needs a fresh displacement candle to create directional edge"

    def _build_invalidation_text(self, bias: str, levels: Dict[str, float], orderflow: Dict[str, Any]) -> str:
        if bias == "bullish":
            return (
                f"Bullish thesis weakens on loss of pivot {levels['pivot']} and especially on acceptance below "
                f"support_1 {levels['support_1']} with seller_pressure or seller_aggression confirmation."
            )
        if bias == "bearish":
            return (
                f"Bearish thesis weakens on reclaim of pivot {levels['pivot']} and especially on acceptance above "
                f"resistance_1 {levels['resistance_1']} with buyer_pressure or buyer_aggression confirmation."
            )
        return (
            f"Neutral thesis invalidates only when price leaves the {levels['support_1']} / {levels['resistance_1']} "
            f"range with clear {orderflow['delta_pressure']}."
        )

    def _build_execution_note(
        self,
        token: str,
        interval: str,
        signal: str,
        bias: str,
        confidence: int,
        indicators: Dict[str, Any],
        orderflow: Dict[str, Any],
        confluence: Dict[str, Any],
        volatility: Dict[str, Any],
        setup_replay: Dict[str, Any],
    ) -> str:
        replay_text = ""
        if setup_replay.get("count"):
            replay_text = (
                f" Replay memory: {setup_replay['count']} setups, "
                f"winrate={setup_replay.get('winrate', 'n/a')}%, "
                f"best_bias={setup_replay.get('best_bias', 'n/a')}."
            )

        return (
            f"{token} {interval} | signal={signal} | bias={bias} | confidence={confidence}% | "
            f"trend={indicators['trend']} | RSI={indicators['rsi']} | MFI={indicators['mfi']} | "
            f"orderflow={orderflow['dominant_signal']} ({orderflow['delta_pressure']}) | "
            f"confluence={confluence.get('score', 'n/a')} | volatility={volatility['regime']}. "
            f"Execution style: wait for confirmation candle in direction of the dominant orderflow, avoid entries when exhaustion is active, "
            f"and downgrade aggressiveness when volume acceleration falls below 1.0.{replay_text}"
        )

    def _build_premium_payload(
        self,
        token: str,
        interval: str,
        indicators: Dict[str, Any],
        orderflow: Dict[str, Any],
        levels: Dict[str, float],
        multi_timeframe: Optional[Dict[str, Any]],
        market_structure: Dict[str, Any],
    ) -> Dict[str, Any]:
        tf_data = multi_timeframe["timeframes"] if multi_timeframe else {}

        def bias_label(tf: str) -> str:
            item = tf_data.get(tf, {})
            return item.get("bias", "unknown")

        rsi_state = "bullish" if indicators["rsi"] >= 55 else "bearish" if indicators["rsi"] <= 45 else "neutral"
        mfi_state = "supported" if indicators["mfi"] >= 55 else "weak" if indicators["mfi"] <= 45 else "neutral"
        macd_state = "positive_cross" if indicators["macd"] > indicators["macd_signal"] else "negative_cross"
        volume_state = "expansion" if indicators["volume_ratio"] >= 1.2 else "normal"

        ai_context = (
            f"{token} {interval}: structure={market_structure['structure']}, momentum={market_structure['momentum']}, "
            f"trend={indicators['trend']}, rsi={indicators['rsi']}, mfi={indicators['mfi']}, "
            f"orderflow={orderflow['dominant_signal']}, confluence={multi_timeframe['confluence']['score'] if multi_timeframe else 'n/a'}."
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
                "market_structure": market_structure["structure"],
                "momentum": market_structure["momentum"],
            },
            "premium_ai_context": ai_context,
            "liquidity_map": {
                "pivot": levels["pivot"],
                "resistance_cluster": [levels["resistance_1"], levels["resistance_2"]],
                "support_cluster": [levels["support_1"], levels["support_2"]],
            },
            "orderflow_map": {
                "delta_pressure": orderflow["delta_pressure"],
                "imbalance_zone": orderflow["imbalance_zone"],
                "close_position": orderflow["close_position"],
                "body_ratio": orderflow["body_ratio"],
                "volume_acceleration": orderflow["volume_acceleration"],
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
        market_structure: Dict[str, Any],
    ) -> Dict[str, Any]:
        confluence_score = multi_timeframe["confluence"]["score"] if multi_timeframe else confidence
        vip_score = int(round(
            (confidence * 0.40)
            + (confluence_score * 0.35)
            + (orderflow["strength"] * 0.15)
            + (market_structure["score"] * 0.10)
        ))
        vip_score = int(self._clamp(vip_score, 40, 98))

        execution_mode = "aggressive_selective" if vip_score >= 82 else "selective" if vip_score >= 68 else "defensive"
        risk_profile = "controlled" if volatility["regime"] == "low" else "adaptive" if volatility["regime"] == "medium" else "high_volatility"

        bull_scenario = (
            f"Maintien au-dessus de {levels['pivot']} puis extension vers {levels['resistance_1']} / {levels['resistance_2']} "
            f"si {orderflow['delta_pressure']} reste orienté acheteur et que la clôture reste haute dans la bougie."
        )
        bear_scenario = (
            f"Perte de {levels['pivot']} puis pression vers {levels['support_1']} / {levels['support_2']} "
            f"si seller aggression domine et que l'acceptation sous pivot se confirme."
        )
        neutral_scenario = (
            f"Compression entre {levels['support_1']} et {levels['resistance_1']}, attendre une expansion du body et une accélération de volume."
        )

        desk_notes = (
            f"{token} {interval} | signal={signal} | bias={bias} | structure={market_structure['structure']} | "
            f"confluence={confluence_score} | dominant_flow={orderflow['dominant_signal']} | volatility={volatility['regime']}."
        )

        telegram_ready = bool(
            vip_score >= 80
            and confluence_score >= 75
            and signal == "buy"
            and not orderflow["exhaustion"]
        )

        return {
            "score": vip_score,
            "execution_mode": execution_mode,
            "risk_profile": risk_profile,
            "bullish_scenario": bull_scenario,
            "bearish_scenario": bear_scenario,
            "neutral_scenario": neutral_scenario,
            "desk_notes": desk_notes,
            "telegram_alert_candidate": telegram_ready,
            "invalidation_map": {
                "bull": levels["support_1"],
                "bear": levels["resistance_1"],
                "pivot": levels["pivot"],
            },
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
        """
        Replay propre basé sur les vrais trades en base de données.

        IMPORTANT:
        - On ne crée plus de faux historique dans setup_replay.json.
        - On ne compte que les Signal actifs: is_deleted=False.
        - Donc un trade supprimé depuis l'admin ne compte plus dans:
          count, winrate, avg_confidence, last_setups, best_bias.
        """
        try:
            from app.models import Signal
        except Exception:
            return {
                "count": 0,
                "winrate": None,
                "avg_confidence": None,
                "last_setups": [],
                "best_bias": None,
            }

        token = (token or "").upper().strip()
        interval = (interval or "").lower().strip()

        asset_aliases = {
            "BTC": ["BTC", "BTCUSD", "BTCUSDT"],
            "ETH": ["ETH", "ETHUSD", "ETHUSDT"],
            "SOL": ["SOL", "SOLUSD", "SOLUSDT"],
            "XRP": ["XRP", "XRPUSD", "XRPUSDT"],
            "BNB": ["BNB", "BNBUSD", "BNBUSDT"],
            "DOGE": ["DOGE", "DOGEUSD", "DOGEUSDT"],
            "ADA": ["ADA", "ADAUSD", "ADAUSDT"],
            "AVAX": ["AVAX", "AVAXUSD", "AVAXUSDT"],
            "LINK": ["LINK", "LINKUSD", "LINKUSDT"],
            "MATIC": ["MATIC", "MATICUSD", "MATICUSDT"],
            "TRX": ["TRX", "TRXUSD", "TRXUSDT"],
            "LTC": ["LTC", "LTCUSD", "LTCUSDT"],
            "DOT": ["DOT", "DOTUSD", "DOTUSDT"],
            "UNI": ["UNI", "UNIUSD", "UNIUSDT"],
            "ATOM": ["ATOM", "ATOMUSD", "ATOMUSDT"],
            "GOLD": ["GOLD", "XAUUSD"],
            "US100": ["US100", "NAS100"],
        }

        assets = asset_aliases.get(token, [token])

        # 1) Essai précis: actif + timeframe sélectionné
        query = (
            Signal.query
            .filter(
                Signal.is_deleted == False,
                Signal.asset.in_(assets)
            )
        )

        if interval:
            query = query.filter(
                (Signal.timeframe == interval) |
                (Signal.timeframe == interval.upper())
            )

        trades = (
            query
            .order_by(Signal.created_at.asc())
            .all()
        )

        # 2) Fallback: même actif, tous timeframes
        # Important: évite d'afficher 0 juste parce que l'analyse est en 1h
        # alors que les signaux BTC sont enregistrés en M15/H1/None/etc.
        if not trades:
            trades = (
                Signal.query
                .filter(
                    Signal.is_deleted == False,
                    Signal.asset.in_(assets)
                )
                .order_by(Signal.created_at.asc())
                .all()
            )

        # 3) Fallback global: tous les trades actifs
        # Important: garde la section Replay utile même si l'actif analysé
        # n'a pas encore d'historique dans la base.
        if not trades:
            trades = (
                Signal.query
                .filter(Signal.is_deleted == False)
                .order_by(Signal.created_at.asc())
                .all()
            )

        if not trades:
            return {
                "count": 0,
                "winrate": None,
                "avg_confidence": None,
                "last_setups": [],
                "best_bias": None,
            }

        closed_trades = [
            t for t in trades
            if (t.status or "").upper() in {"WIN", "LOSS"}
            or t.result_percent is not None
        ]

        wins = 0
        scored = 0
        confidences: List[float] = []
        bullish = 0
        bearish = 0

        for trade in trades:
            try:
                confidences.append(float(trade.confidence or 0))
            except Exception:
                pass

            action = (trade.action or "").upper()
            trend = (trade.market_trend or "").lower()
            status = (trade.status or "").upper()

            if action == "BUY" or trend in {"bullish", "haussier", "bull"}:
                bullish += 1
            elif action == "SELL" or trend in {"bearish", "baissier", "bear"}:
                bearish += 1

            if status in {"WIN", "LOSS"}:
                scored += 1
                if status == "WIN":
                    wins += 1
            elif trade.result_percent is not None:
                scored += 1
                if float(trade.result_percent or 0) > 0:
                    wins += 1

        best_bias = "bullish" if bullish > bearish else "bearish" if bearish > bullish else "mixed"

        def _trade_outcome_pct(trade) -> Optional[float]:
            if trade.result_percent is not None:
                try:
                    return round(float(trade.result_percent), 2)
                except Exception:
                    return None

            try:
                entry = float(trade.entry_price or 0)
                if entry <= 0:
                    return None

                status = (trade.status or "").upper()
                action = (trade.action or "BUY").upper()

                if status == "WIN" and trade.take_profit is not None:
                    exit_price = float(trade.take_profit)
                elif status == "LOSS" and trade.stop_loss is not None:
                    exit_price = float(trade.stop_loss)
                else:
                    return None

                if action == "BUY":
                    return round(((exit_price - entry) / entry) * 100, 2)

                return round(((entry - exit_price) / entry) * 100, 2)
            except Exception:
                return None

        last_source = closed_trades[-5:] if closed_trades else trades[-5:]

        last_setups = []
        for trade in last_source:
            trade_action = (trade.action or signal or "neutral").lower()
            trade_trend = (trade.market_trend or "").lower()

            if trade_action == "buy":
                row_bias = "bullish"
            elif trade_action == "sell":
                row_bias = "bearish"
            elif trade_trend in {"bullish", "haussier", "bull"}:
                row_bias = "bullish"
            elif trade_trend in {"bearish", "baissier", "bear"}:
                row_bias = "bearish"
            else:
                row_bias = "mixed"

            last_setups.append({
                "timestamp": int(trade.created_at.timestamp()) if trade.created_at else None,
                "token": token,
                "interval": trade.timeframe or interval or "1h",
                "signal": trade_action,
                "bias": row_bias,
                "confidence": round(float(trade.confidence or 0), 2),
                "price": round(float(trade.entry_price or 0), 6),
                "orderflow_state": orderflow.get("state") if isinstance(orderflow, dict) else None,
                "orderflow_strength": orderflow.get("strength") if isinstance(orderflow, dict) else None,
                "orderflow_signal": orderflow.get("dominant_signal") if isinstance(orderflow, dict) else None,
                "delta_pressure": orderflow.get("delta_pressure") if isinstance(orderflow, dict) else None,
                "confluence_score": (
                    multi_timeframe.get("confluence", {}).get("score")
                    if isinstance(multi_timeframe, dict)
                    else None
                ),
                "simulated_outcome_pct": _trade_outcome_pct(trade),
            })

        return {
            "count": len(trades),
            "winrate": round((wins / scored) * 100, 2) if scored else None,
            "avg_confidence": round(sum(confidences) / len(confidences), 2) if confidences else None,
            "last_setups": last_setups,
            "best_bias": best_bias,
        }

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
                "ai_advanced_analysis": data["ai_advanced_analysis"],
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
                "ai_advanced_analysis": data["ai_advanced_analysis"],
            },
        }

    def _cg_headers(self) -> Dict[str, str]:
        headers = {"accept": "application/json"}
        if self.coingecko_api_key:
            headers["x-cg-demo-api-key"] = self.coingecko_api_key
        return headers

    @staticmethod
    def _safe_div(num: float, den: float) -> float:
        if den == 0:
            return 0.0
        return float(num / den)

    @staticmethod
    def _clamp(value: float, min_value: float, max_value: float) -> float:
        return max(min_value, min(max_value, value))

    @staticmethod
    def _pct(delta: float, base: float) -> float:
        if base == 0:
            return 0.0
        return float(delta / base) * 100.0