from flask import Blueprint, jsonify
import requests
import time
import threading

market_ticker_bp = Blueprint("market_ticker", __name__)

# Cache thread-safe en memoire (survit aux requetes, pas aux restarts)
_cache_lock = threading.Lock()
_CACHE = {"time": 0, "data": None}
_CACHE_TTL = 60  # secondes


def _fetch_binance_prices():
    """
    Binance API — gratuite, pas de rate limit, fiable sur Render.
    Retourne dict {symbol: {price, change}}
    """
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    url = "https://api.binance.com/api/v3/ticker/24hr"
    params = {"symbols": str(symbols).replace("'", '"').replace(" ", "")}

    r = requests.get(url, params=params, timeout=8)
    r.raise_for_status()
    data = r.json()

    result = {}
    name_map = {
        "BTCUSDT": "BTC", "ETHUSDT": "ETH",
        "SOLUSDT": "SOL", "BNBUSDT": "BNB", "XRPUSDT": "XRP"
    }
    for item in data:
        sym = name_map.get(item["symbol"])
        if sym:
            result[sym] = {
                "price": float(item["lastPrice"]),
                "change": float(item["priceChangePercent"])
            }
    return result


def _fetch_yahoo_price(symbol):
    """Yahoo Finance pour GOLD et US100 (indices TradFi)."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=6)
    meta = r.json()["chart"]["result"][0]["meta"]
    price = meta.get("regularMarketPrice") or meta.get("previousClose")
    change_pct = None
    prev = meta.get("previousClose")
    curr = meta.get("regularMarketPrice")
    if prev and curr and prev != 0:
        change_pct = round((curr - prev) / prev * 100, 2)
    return {"price": price, "change": change_pct}


def _build_ticker():
    items = []

    # 1. Crypto via Binance (principal)
    try:
        crypto = _fetch_binance_prices()
        for sym in ["BTC", "ETH", "SOL", "BNB", "XRP"]:
            d = crypto.get(sym, {})
            items.append({
                "symbol": sym,
                "price": round(d["price"], 2) if d.get("price") else None,
                "change": round(d["change"], 2) if d.get("change") is not None else None
            })
    except Exception:
        # Fallback CoinGecko si Binance echoue
        try:
            cg_url = (
                "https://api.coingecko.com/api/v3/simple/price"
                "?ids=bitcoin,ethereum,solana,binancecoin,ripple"
                "&vs_currencies=usd&include_24hr_change=true"
            )
            crypto = requests.get(cg_url, timeout=8).json()
            mapping = {
                "bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL",
                "binancecoin": "BNB", "ripple": "XRP"
            }
            for coin_id, sym in mapping.items():
                d = crypto.get(coin_id, {})
                items.append({
                    "symbol": sym,
                    "price": d.get("usd"),
                    "change": round(d.get("usd_24h_change", 0), 2)
                })
        except Exception:
            for sym in ["BTC", "ETH", "SOL", "BNB", "XRP"]:
                items.append({"symbol": sym, "price": None, "change": None})

    # 2. GOLD via Yahoo
    try:
        gold = _fetch_yahoo_price("GC=F")
        items.append({"symbol": "GOLD", "price": gold["price"], "change": gold["change"]})
    except Exception:
        items.append({"symbol": "GOLD", "price": None, "change": None})

    # 3. US100 via Yahoo
    try:
        us100 = _fetch_yahoo_price("%5ENDX")
        items.append({"symbol": "US100", "price": us100["price"], "change": us100["change"]})
    except Exception:
        items.append({"symbol": "US100", "price": None, "change": None})

    # 4. SP500 via Yahoo
    try:
        sp500 = _fetch_yahoo_price("%5EGSPC")
        items.append({"symbol": "SP500", "price": sp500["price"], "change": sp500["change"]})
    except Exception:
        items.append({"symbol": "SP500", "price": None, "change": None})

    return {"items": items, "updated_at": int(time.time())}


@market_ticker_bp.route("/api/market-ticker")
def market_ticker():
    now = time.time()

    with _cache_lock:
        if _CACHE["data"] and now - _CACHE["time"] < _CACHE_TTL:
            return jsonify(_CACHE["data"])

    # Fetch hors du lock pour ne pas bloquer les autres requetes
    try:
        result = _build_ticker()
    except Exception:
        with _cache_lock:
            if _CACHE["data"]:
                return jsonify(_CACHE["data"])
        return jsonify({"items": [], "updated_at": int(now)}), 503

    with _cache_lock:
        _CACHE["time"] = now
        _CACHE["data"] = result

    return jsonify(result)


@market_ticker_bp.route("/api/market-live")
def market_live():
    """
    Endpoint supplementaire pour la homepage — renvoie BTC, ETH, BTC.D, F&G.
    Cache 60s. Utilise Binance pour les prix, alternative.me pour F&G.
    """
    now = time.time()

    # Reutilise le meme cache que le ticker
    with _cache_lock:
        if _CACHE["data"] and now - _CACHE["time"] < _CACHE_TTL:
            ticker_data = _CACHE["data"]
        else:
            ticker_data = None

    if not ticker_data:
        try:
            ticker_data = _build_ticker()
            with _cache_lock:
                _CACHE["time"] = now
                _CACHE["data"] = ticker_data
        except Exception:
            ticker_data = {"items": []}

    # Extraire BTC et ETH du ticker
    prices = {i["symbol"]: i for i in ticker_data.get("items", [])}

    # Fear & Greed (cache separe)
    try:
        fg = requests.get("https://api.alternative.me/fng/?limit=1", timeout=6).json()
        fg_data = fg["data"][0]
        fear_value = int(fg_data["value"])
        fear_label = fg_data["value_classification"]
    except Exception:
        fear_value = None
        fear_label = "N/A"

    btc = prices.get("BTC", {})
    eth = prices.get("ETH", {})

    return jsonify({
        "btc": {
            "price": btc.get("price"),
            "change": btc.get("change")
        },
        "eth": {
            "price": eth.get("price"),
            "change": eth.get("change")
        },
        "fear_greed": {
            "value": fear_value,
            "label": fear_label
        },
        "updated_at": int(now)
    })
