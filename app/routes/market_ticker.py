from flask import Blueprint, jsonify
import requests
import time

market_ticker_bp = Blueprint("market_ticker", __name__)

CACHE = {
    "time": 0,
    "data": None
}

def yahoo_price(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    r = requests.get(url, timeout=6)
    data = r.json()
    return data["chart"]["result"][0]["meta"].get("regularMarketPrice")

@market_ticker_bp.route("/api/market-ticker")
def market_ticker():
    now = time.time()

    if CACHE["data"] and now - CACHE["time"] < 60:
        return jsonify(CACHE["data"])

    items = []

    try:
        cg_url = (
            "https://api.coingecko.com/api/v3/simple/price"
            "?ids=bitcoin,ethereum,solana,binancecoin,ripple"
            "&vs_currencies=usd"
            "&include_24hr_change=true"
        )
        crypto = requests.get(cg_url, timeout=6).json()

        mapping = {
            "bitcoin": "BTC",
            "ethereum": "ETH",
            "solana": "SOL",
            "binancecoin": "BNB",
            "ripple": "XRP"
        }

        for coin_id, symbol in mapping.items():
            coin = crypto.get(coin_id, {})
            items.append({
                "symbol": symbol,
                "price": coin.get("usd"),
                "change": coin.get("usd_24h_change")
            })
    except Exception:
        pass

    try:
        items.append({
            "symbol": "GOLD",
            "price": yahoo_price("GC=F"),
            "change": None
        })
    except Exception:
        items.append({"symbol": "GOLD", "price": None, "change": None})

    try:
        items.append({
            "symbol": "US100",
            "price": yahoo_price("%5ENDX"),
            "change": None
        })
    except Exception:
        items.append({"symbol": "US100", "price": None, "change": None})

    try:
        items.append({
            "symbol": "US500",
            "price": yahoo_price("%5EGSPC"),
            "change": None
        })
    except Exception:
        items.append({"symbol": "US500", "price": None, "change": None})

    result = {"items": items}
    CACHE["time"] = now
    CACHE["data"] = result

    return jsonify(result)