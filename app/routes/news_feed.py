import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from flask import Blueprint, render_template, jsonify
from flask_login import current_user

news_feed_bp = Blueprint("news_feed", __name__, url_prefix="/explore")

CACHE_SECONDS = 1800

_CACHE = {"ts": 0, "data": None}

_LAST_GOOD = {
    "global_market": None,
    "markets": None,
    "trending": None,
    "news": None
}


def safe_float(value, default=0):
    try:
        return float(value)
    except Exception:
        return default


def money_short(value):
    value = safe_float(value)

    if value >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"

    return f"${value:,.0f}"


def percent(value):
    value = safe_float(value)
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def get_json(url, params=None, timeout=12):
    response = requests.get(
        url,
        params=params,
        timeout=timeout,
        headers={"User-Agent": "VelwolfSignals/1.0"}
    )
    response.raise_for_status()
    return response.json()


def user_has_watchlist_access(user):
    if not user or not getattr(user, "is_authenticated", False):
        return False

    plan = (getattr(user, "plan", "") or "").strip().lower()
    return plan in ["premium", "vip"]


def detect_sentiment(text):
    text = (text or "").lower()

    negative_words = [
        "hack", "exploit", "lawsuit", "drop", "falls", "crash",
        "selloff", "liquidation", "fear", "risk", "ban", "fraud",
        "attack", "loss", "decline", "warning", "probe",
        "investigation", "bearish", "stalled", "threatens"
    ]

    positive_words = [
        "surge", "rally", "gain", "growth", "approval", "etf",
        "record", "bullish", "institutional", "adoption",
        "breakout", "raises", "launch", "partnership",
        "accumulation", "rebound", "confirms"
    ]

    negative_score = sum(1 for word in negative_words if word in text)
    positive_score = sum(1 for word in positive_words if word in text)

    if positive_score > negative_score:
        return "positive"
    if negative_score > positive_score:
        return "negative"
    return "neutral"


def extract_coin(text):
    text = (text or "").upper()

    coins = [
        "BTC", "ETH", "SOL", "XRP", "BNB", "ADA", "DOGE",
        "LINK", "AVAX", "TRX", "USDT", "USDC"
    ]

    names = {
        "BITCOIN": "BTC",
        "ETHEREUM": "ETH",
        "SOLANA": "SOL",
        "RIPPLE": "XRP",
        "BINANCE": "BNB",
        "CARDANO": "ADA",
        "DOGECOIN": "DOGE",
        "CHAINLINK": "LINK",
        "AVALANCHE": "AVAX",
        "TRON": "TRX",
        "TETHER": "USDT",
        "USD COIN": "USDC"
    }

    for coin in coins:
        if coin in text:
            return coin

    for name, symbol in names.items():
        if name in text:
            return symbol

    return "MARKET"


def load_global_market():
    try:
        data = get_json("https://api.coingecko.com/api/v3/global")
        global_data = data.get("data", {})

        market_cap = global_data.get("total_market_cap", {}).get("usd", 0)
        volume = global_data.get("total_volume", {}).get("usd", 0)
        btc_dominance = global_data.get("market_cap_percentage", {}).get("btc", 0)
        eth_dominance = global_data.get("market_cap_percentage", {}).get("eth", 0)

        result = {
            "market_cap": money_short(market_cap),
            "volume": money_short(volume),
            "btc_dominance": percent(btc_dominance),
            "eth_dominance": percent(eth_dominance),
        }

        _LAST_GOOD["global_market"] = result
        return result

    except Exception as e:
        print("COINGECKO GLOBAL ERROR:", e)

        if _LAST_GOOD["global_market"]:
            return _LAST_GOOD["global_market"]

        return {
            "market_cap": "$0",
            "volume": "$0",
            "btc_dominance": "0.00%",
            "eth_dominance": "0.00%",
        }


def load_markets():
    try:
        coins = get_json(
            "https://api.coingecko.com/api/v3/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 12,
                "page": 1,
                "sparkline": "true",
                "price_change_percentage": "24h,7d"
            }
        )

        max_market_cap = max(
            [safe_float(coin.get("market_cap")) for coin in coins] or [1]
        )

        result = []

        for coin in coins:
            market_cap = safe_float(coin.get("market_cap"))
            volume = safe_float(coin.get("total_volume"))
            change_24h = safe_float(coin.get("price_change_percentage_24h"))
            change_7d = safe_float(coin.get("price_change_percentage_7d_in_currency"))

            bar_width = (market_cap / max_market_cap) * 100 if max_market_cap else 8
            bar_width = max(8, min(bar_width, 100))

            result.append({
                "id": coin.get("id"),
                "symbol": coin.get("symbol", "").upper(),
                "name": coin.get("name"),
                "image": coin.get("image"),
                "price": safe_float(coin.get("current_price")),
                "price_display": f"${safe_float(coin.get('current_price')):,.4f}",
                "market_cap": market_cap,
                "market_cap_display": money_short(market_cap),
                "volume": volume,
                "volume_display": money_short(volume),
                "change_24h": change_24h,
                "change_7d": change_7d,
                "bar_width": bar_width,
                "sparkline": coin.get("sparkline_in_7d", {}).get("price", [])[-30:],
            })

        if result:
            _LAST_GOOD["markets"] = result

        return result

    except Exception as e:
        print("COINGECKO MARKETS ERROR:", e)

        if _LAST_GOOD["markets"]:
            return _LAST_GOOD["markets"]

        return []


def load_trending():
    try:
        data = get_json("https://api.coingecko.com/api/v3/search/trending")
        coins = data.get("coins", [])

        trending = []

        for item in coins[:10]:
            coin = item.get("item", {})
            trending.append({
                "symbol": coin.get("symbol", "").upper(),
                "name": coin.get("name"),
                "market_cap_rank": coin.get("market_cap_rank"),
                "thumb": coin.get("thumb"),
                "score": coin.get("score", 0),
            })

        if trending:
            _LAST_GOOD["trending"] = trending

        return trending

    except Exception as e:
        print("COINGECKO TRENDING ERROR:", e)

        if _LAST_GOOD["trending"]:
            return _LAST_GOOD["trending"]

        return []


def load_news_from_rss():
    feeds = [
        ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
        ("Cointelegraph", "https://cointelegraph.com/rss"),
        ("Decrypt", "https://decrypt.co/feed"),
    ]

    news = []

    for source_name, url in feeds:
        try:
            response = requests.get(
                url,
                timeout=10,
                headers={"User-Agent": "VelwolfSignals/1.0"}
            )
            response.raise_for_status()

            root = ET.fromstring(response.content)

            for item in root.findall(".//item")[:10]:
                title = item.findtext("title") or ""
                link = item.findtext("link") or "#"
                pub_date = item.findtext("pubDate") or ""

                news.append({
                    "title": title.strip(),
                    "url": link.strip(),
                    "source": source_name,
                    "published_at": pub_date,
                    "coin": extract_coin(title),
                    "topic": "market",
                    "sentiment": detect_sentiment(title),
                })

        except Exception as e:
            print(f"RSS ERROR {source_name}:", e)

    news = news[:6]

    if news:
        _LAST_GOOD["news"] = news
        return news

    if _LAST_GOOD["news"]:
        return _LAST_GOOD["news"]

    return []


def build_summary(markets, news):
    positive = sum(1 for item in news if item.get("sentiment") == "positive")
    negative = sum(1 for item in news if item.get("sentiment") == "negative")
    neutral = sum(1 for item in news if item.get("sentiment") == "neutral")

    strongest = max(markets, key=lambda x: x.get("change_24h", 0)) if markets else None
    weakest = min(markets, key=lambda x: x.get("change_24h", 0)) if markets else None

    if positive > negative:
        bias = "constructif"
    elif negative > positive:
        bias = "défensif"
    else:
        bias = "neutre"

    total = positive + neutral + negative

    return {
        "bias": bias,
        "positive": positive,
        "negative": negative,
        "neutral": neutral,
        "positive_percent": round((positive / total) * 100, 2) if total else 0,
        "neutral_percent": round((neutral / total) * 100, 2) if total else 0,
        "negative_percent": round((negative / total) * 100, 2) if total else 0,
        "strongest": strongest,
        "weakest": weakest,
    }


def build_smart_watchlist(markets, news):
    smart = []

    def add_coin(coin, reason):
        if not coin:
            return

        coin_id = coin.get("id")
        symbol = coin.get("symbol")

        if not coin_id or not symbol:
            return

        if any(item.get("id") == coin_id for item in smart):
            return

        smart.append({
            "id": coin.get("id"),
            "symbol": coin.get("symbol"),
            "name": coin.get("name"),
            "image": coin.get("image"),
            "price": coin.get("price"),
            "price_display": coin.get("price_display"),
            "change_24h": coin.get("change_24h"),
            "change_7d": coin.get("change_7d"),
            "market_cap_display": coin.get("market_cap_display"),
            "volume_display": coin.get("volume_display"),
            "reason": reason,
        })

    coin_by_symbol = {
        (coin.get("symbol") or "").upper(): coin
        for coin in markets
    }

    add_coin(coin_by_symbol.get("BTC"), "Actif directeur du marché")
    add_coin(coin_by_symbol.get("ETH"), "Actif majeur à forte liquidité")
    add_coin(coin_by_symbol.get("SOL"), "Layer 1 à surveiller")

    if markets:
        strongest = max(markets, key=lambda x: x.get("change_24h", 0))
        weakest = min(markets, key=lambda x: x.get("change_24h", 0))

        add_coin(strongest, "Top momentum 24H")
        add_coin(weakest, "Forte pression vendeuse 24H")

    news_symbols = []

    for item in news:
        symbol = (item.get("coin") or "").upper()
        if symbol and symbol != "MARKET":
            news_symbols.append(symbol)

    for symbol in news_symbols:
        add_coin(coin_by_symbol.get(symbol), "Actif cité dans les news")

    for coin in markets[:8]:
        add_coin(coin, "Top capitalisation / forte liquidité")

    return smart[:6]


def build_page_data():
    global_market = load_global_market()
    markets = load_markets()
    trending = load_trending()
    news = load_news_from_rss()
    summary = build_summary(markets, news)
    smart_watchlist = build_smart_watchlist(markets, news)

    return {
        "global_market": global_market,
        "markets": markets,
        "trending": trending,
        "news": news,
        "summary": summary,
        "smart_watchlist": smart_watchlist,
        "watchlist_access": user_has_watchlist_access(current_user),
        "updated_at": datetime.now(timezone.utc).strftime("%H:%M UTC"),
    }


def get_cached_data():
    now = time.time()

    if _CACHE["data"] and now - _CACHE["ts"] < CACHE_SECONDS:
        data = dict(_CACHE["data"])
        data["watchlist_access"] = user_has_watchlist_access(current_user)
        return data

    try:
        data = build_page_data()

        if data.get("markets"):
            cached_data = dict(data)
            cached_data["watchlist_access"] = False

            _CACHE["data"] = cached_data
            _CACHE["ts"] = now

        return data

    except Exception as e:
        print("NEWS FEED BUILD ERROR:", e)

        if _CACHE["data"]:
            data = dict(_CACHE["data"])
            data["watchlist_access"] = user_has_watchlist_access(current_user)
            return data

        return {
            "global_market": {
                "market_cap": "$0",
                "volume": "$0",
                "btc_dominance": "0.00%",
                "eth_dominance": "0.00%",
            },
            "markets": [],
            "trending": [],
            "news": [],
            "summary": build_summary([], []),
            "smart_watchlist": [],
            "watchlist_access": user_has_watchlist_access(current_user),
            "updated_at": datetime.now(timezone.utc).strftime("%H:%M UTC"),
        }


@news_feed_bp.route("/news-feed")
@news_feed_bp.route("/<lang_code>/news-feed")
def news_feed():
    data = get_cached_data()
    return render_template("news_feed.html", **data)


@news_feed_bp.route("/api/news-feed")
def news_feed_api():
    data = get_cached_data()
    return jsonify(data)