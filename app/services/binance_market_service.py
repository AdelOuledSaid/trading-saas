import requests
from datetime import datetime
from typing import List, Dict, Optional


BINANCE_SPOT_BASE_URLS = [
    "https://data-api.binance.vision",  # public market-data mirror, not geo-restricted
    "https://api.binance.com",          # fallback (geo-blocked from some IPs -> HTTP 451)
]


INTERVAL_MAP = {
    "1": "1m",
    "1m": "1m",
    "3m": "3m",
    "5": "5m",
    "5m": "5m",
    "15": "15m",
    "15m": "15m",
    "30m": "30m",
    "60": "1h",
    "1h": "1h",
    "240": "4h",
    "4h": "4h",
    "1d": "1d",
}


SYMBOL_MAP = {
    "BTCUSD": "BTCUSDT",
    "ETHUSD": "ETHUSDT",
    "GOLD": None,
    "US100": None,
}


class BinanceMarketServiceError(Exception):
    pass


def map_signal_asset_to_binance_symbol(asset: str) -> Optional[str]:
    return SYMBOL_MAP.get((asset or "").upper())


def map_timeframe_to_binance_interval(timeframe: str) -> str:
    return INTERVAL_MAP.get((timeframe or "15m").lower(), "15m")


def fetch_klines(
    symbol: str,
    interval: str,
    start_time_ms: int,
    end_time_ms: int,
    limit: int = 300,
    use_ui_klines: bool = True,
    timeout: int = 10,
) -> List[Dict]:
    endpoint = "/api/v3/uiKlines" if use_ui_klines else "/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_time_ms,
        "endTime": end_time_ms,
        "limit": min(limit, 1000),
    }

    # Binance geo-restricts api.binance.com from many cloud/datacenter IPs
    # (HTTP 451). The data-api.binance.vision mirror serves the same public
    # market data without that restriction, so we try it first.
    data = None
    last_error = "no base url tried"
    for base in BINANCE_SPOT_BASE_URLS:
        try:
            response = requests.get(f"{base}{endpoint}", params=params, timeout=timeout)
        except requests.RequestException as exc:
            last_error = repr(exc)
            continue

        if response.status_code == 200:
            payload = response.json()
            if isinstance(payload, list):
                data = payload
                break
            last_error = "Unexpected Binance response format."
        else:
            last_error = f"{response.status_code}: {response.text[:200]}"

    if data is None:
        raise BinanceMarketServiceError(f"Binance klines error {last_error}")

    candles: List[Dict] = []
    for idx, row in enumerate(data):
        # Binance kline array format:
        # [
        #   open_time, open, high, low, close, volume,
        #   close_time, quote_asset_volume, number_of_trades,
        #   taker_buy_base_asset_volume, taker_buy_quote_asset_volume, ignore
        # ]
        candles.append(
            {
                "position_index": idx,
                "open_time": int(row[0]),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]) if row[5] is not None else None,
                "close_time": int(row[6]),
            }
        )

    return candles


def dt_to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)