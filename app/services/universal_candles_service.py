import os
from datetime import datetime, timezone
import requests

# =========================
# CONFIG
# =========================
BINANCE_URL = "https://api.binance.com/api/v3/klines"
TWELVE_URL = "https://api.twelvedata.com/time_series"

TWELVE_API_KEY = os.getenv("TWELVEDATA_API_KEY")


# =========================
# HELPERS
# =========================
def _to_iso(dt_obj):
    if not dt_obj:
        return None

    if isinstance(dt_obj, str):
        return dt_obj

    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=timezone.utc)

    return dt_obj.isoformat()


def _to_binance_ms(dt_obj):
    if not dt_obj:
        return None

    if isinstance(dt_obj, str):
        dt_obj = datetime.fromisoformat(dt_obj)

    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=timezone.utc)

    return int(dt_obj.timestamp() * 1000)


def _normalize_twelve_datetime(value):
    try:
        dt_obj = datetime.fromisoformat(value)
    except Exception:
        try:
            dt_obj = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return value

    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=timezone.utc)

    return dt_obj.isoformat()


# =========================
# MAIN ENTRY (GLOBAL)
# =========================
def fetch_candles(asset, timeframe="15m", limit=200, start_time=None, end_time=None):
    asset = (asset or "").upper()

    try:
        if asset in [
            "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "BNBUSD", "ADAUSD", "DOGEUSD", "AVAXUSD",
            "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "ADAUSDT", "DOGEUSDT", "AVAXUSDT"
        ]:
            return fetch_binance(asset, timeframe, limit, start_time=start_time, end_time=end_time)

        elif asset in [
            "GOLD", "XAUUSD", "US100", "US500", "FRA40", "GER40", "UK100", "JPN225",
            "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD", "EURJPY"
        ]:
            return fetch_twelve_data(asset, timeframe, limit, start_time=start_time, end_time=end_time)

        else:
            raise Exception(f"Asset non supporté: {asset}")

    except Exception as e:
        print("fetch_candles error:", e)
        return []


# =========================
# BINANCE SECTION
# =========================
def map_binance_symbol(asset):
    mapping = {
        "BTCUSD": "BTCUSDT",
        "ETHUSD": "ETHUSDT",
        "SOLUSD": "SOLUSDT",
        "XRPUSD": "XRPUSDT",
        "BNBUSD": "BNBUSDT",
        "ADAUSD": "ADAUSDT",
        "DOGEUSD": "DOGEUSDT",
        "AVAXUSD": "AVAXUSDT",
    }
    return mapping.get(asset, asset)


def convert_binance_timeframe(tf):
    mapping = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "4h": "4h",
        "1d": "1d"
    }
    return mapping.get((tf or "").lower(), "15m")


def fetch_binance(asset, timeframe, limit, start_time=None, end_time=None):
    symbol = map_binance_symbol(asset)
    interval = convert_binance_timeframe(timeframe)

    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": min(max(int(limit or 200), 1), 1000)
    }

    start_ms = _to_binance_ms(start_time)
    end_ms = _to_binance_ms(end_time)

    if start_ms:
        params["startTime"] = start_ms
    if end_ms:
        params["endTime"] = end_ms

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(
        BINANCE_URL,
        params=params,
        headers=headers,
        timeout=15
    )

    if response.status_code != 200:
        raise Exception(f"Erreur Binance API: {response.status_code} - {response.text}")

    data = response.json()

    candles = []
    for k in data:
        candles.append({
            "time": datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc).isoformat(),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]) if len(k) > 5 else None,
        })

    return candles


# =========================
# TWELVE DATA SECTION
# =========================
def map_twelve_symbol(asset):
    mapping = {
        "GOLD": "XAU/USD",
        "XAUUSD": "XAU/USD",
        "US100": "NASDAQ",
        "US500": "SPX",
        "FRA40": "CAC40",
        "GER40": "DAX",
        "UK100": "FTSE",
        "JPN225": "NIKKEI",
        "EURUSD": "EUR/USD",
        "GBPUSD": "GBP/USD",
        "USDJPY": "USD/JPY",
        "USDCHF": "USD/CHF",
        "AUDUSD": "AUD/USD",
        "USDCAD": "USD/CAD",
        "NZDUSD": "NZD/USD",
        "EURJPY": "EUR/JPY",
    }
    return mapping.get(asset, "XAU/USD")


def convert_twelve_timeframe(tf):
    mapping = {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "1h",
        "4h": "4h",
        "1d": "1day"
    }
    return mapping.get((tf or "").lower(), "15min")


def fetch_twelve_data(asset, timeframe, limit, start_time=None, end_time=None):
    if not TWELVE_API_KEY:
        raise Exception("TWELVEDATA_API_KEY manquante dans les variables d’environnement")

    symbol = map_twelve_symbol(asset)
    interval = convert_twelve_timeframe(timeframe)

    params = {
        "symbol": symbol,
        "interval": interval,
        "apikey": TWELVE_API_KEY,
        "outputsize": min(max(int(limit or 200), 1), 5000),
        "format": "JSON",
        "order": "ASC"
    }

    start_iso = _to_iso(start_time)
    end_iso = _to_iso(end_time)

    if start_iso:
        params["start_date"] = start_iso
    if end_iso:
        params["end_date"] = end_iso

    response = requests.get(TWELVE_URL, params=params, timeout=15)

    if response.status_code != 200:
        raise Exception(f"Erreur TwelveData API: {response.status_code} - {response.text}")

    data = response.json()

    if "values" not in data:
        raise Exception(f"TwelveData error: {data}")

    candles = []
    for v in data["values"]:
        candles.append({
            "time": _normalize_twelve_datetime(v["datetime"]),
            "open": float(v["open"]),
            "high": float(v["high"]),
            "low": float(v["low"]),
            "close": float(v["close"]),
            "volume": float(v["volume"]) if v.get("volume") not in [None, ""] else None,
        })

    return candles