import os
import requests
from datetime import datetime
from typing import List, Dict, Optional


TWELVEDATA_BASE_URL = "https://api.twelvedata.com"
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "").strip()


SYMBOL_MAP = {
    "GOLD": "XAU/USD",
    "US100": "NDX",
    "US500": "SPX",
    "FRA40": "FCHI",
}


INTERVAL_MAP = {
    "1": "1min",
    "1m": "1min",
    "3m": "5min",
    "5": "5min",
    "5m": "5min",
    "15": "15min",
    "15m": "15min",
    "30": "30min",
    "30m": "30min",
    "60": "1h",
    "1h": "1h",
    "4h": "4h",
    "1d": "1day",
}


class TwelveDataMarketServiceError(Exception):
    pass


def map_signal_asset_to_twelvedata_symbol(asset: str) -> Optional[str]:
    return SYMBOL_MAP.get((asset or "").upper())


def map_timeframe_to_twelvedata_interval(timeframe: str) -> str:
    return INTERVAL_MAP.get((timeframe or "15m").lower(), "15min")


def _require_api_key() -> None:
    if not TWELVEDATA_API_KEY:
        raise TwelveDataMarketServiceError(
            "TWELVEDATA_API_KEY manquant. Ajoute la variable d'environnement."
        )


def fetch_time_series(
    symbol: str,
    interval: str,
    start_date: datetime,
    end_date: datetime,
    outputsize: int = 300,
    timezone: str = "UTC",
    timeout: int = 15,
) -> List[Dict]:
    _require_api_key()

    url = f"{TWELVEDATA_BASE_URL}/time_series"
    params = {
        "symbol": symbol,
        "interval": interval,
        "start_date": start_date.strftime("%Y-%m-%d %H:%M:%S"),
        "end_date": end_date.strftime("%Y-%m-%d %H:%M:%S"),
        "outputsize": min(outputsize, 5000),
        "timezone": timezone,
        "apikey": TWELVEDATA_API_KEY,
        "format": "JSON",
    }

    response = requests.get(url, params=params, timeout=timeout)
    if response.status_code != 200:
        raise TwelveDataMarketServiceError(
            f"Twelve Data error {response.status_code}: {response.text}"
        )

    data = response.json()

    if "status" in data and data["status"] == "error":
        raise TwelveDataMarketServiceError(
            f"Twelve Data API error: {data.get('message', 'Unknown error')}"
        )

    values = data.get("values")
    if not isinstance(values, list) or not values:
        raise TwelveDataMarketServiceError(
            f"Aucune donnée Twelve Data pour {symbol} ({interval})."
        )

    # Twelve Data renvoie souvent les plus récentes d'abord
    rows = list(reversed(values))

    candles: List[Dict] = []
    for idx, row in enumerate(rows):
        try:
            candles.append(
                {
                    "position_index": idx,
                    "time": row["datetime"],
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]) if row.get("volume") not in [None, ""] else None,
                }
            )
        except (KeyError, TypeError, ValueError) as e:
            raise TwelveDataMarketServiceError(
                f"Donnée bougie invalide reçue de Twelve Data: {row}"
            ) from e

    return candles