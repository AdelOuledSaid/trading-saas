import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from flask import Blueprint, render_template, jsonify, redirect, url_for
from flask_login import current_user

news_feed_bp = Blueprint("news_feed", __name__, url_prefix="/explore")

SUPPORTED_LANGS = {"fr", "en", "es", "de", "it", "pt", "ru"}

CACHE_SECONDS = 1800

_CACHE = {"ts": 0, "data": None}

_LAST_GOOD = {
    "global_market": None,
    "markets": None,
    "trending": None,
    "news": None,
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


def get_json(url, params=None, timeout=10):
    response = requests.get(
        url,
        params=params,
        timeout=timeout,
        headers={
            "User-Agent": "VelWolfSignals/1.0",
            "Accept": "application/json,text/plain,*/*",
        },
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
        "investigation", "bearish", "stalled", "threatens",
    ]

    positive_words = [
        "surge", "rally", "gain", "growth", "approval", "etf",
        "record", "bullish", "institutional", "adoption",
        "breakout", "raises", "launch", "partnership",
        "accumulation", "rebound", "confirms",
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
        "LINK", "AVAX", "TRX", "USDT", "USDC",
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
        "USD COIN": "USDC",
    }

    for coin in coins:
        if coin in text:
            return coin

    for name, symbol in names.items():
        if name in text:
            return symbol

    return "MARKET"


def fallback_global_market():
    return _LAST_GOOD["global_market"] or {
        "market_cap": "Unavailable",
        "volume": "Unavailable",
        "btc_dominance": "Unavailable",
        "eth_dominance": "Unavailable",
    }


def fallback_markets():
    return _LAST_GOOD["markets"] or []


def fallback_trending():
    return _LAST_GOOD["trending"] or []


def fallback_news():
    return _LAST_GOOD["news"] or []


def load_global_market():
    try:
        data = get_json("https://api.coingecko.com/api/v3/global", timeout=8)
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
        return fallback_global_market()


def load_markets_from_binance():
    symbols = {
        "BTCUSDT": ("bitcoin", "BTC", "Bitcoin", "https://assets.coingecko.com/coins/images/1/large/bitcoin.png"),
        "ETHUSDT": ("ethereum", "ETH", "Ethereum", "https://assets.coingecko.com/coins/images/279/large/ethereum.png"),
        "SOLUSDT": ("solana", "SOL", "Solana", "https://assets.coingecko.com/coins/images/4128/large/solana.png"),
        "BNBUSDT": ("binancecoin", "BNB", "BNB", "https://assets.coingecko.com/coins/images/825/large/bnb-icon2_2x.png"),
        "XRPUSDT": ("ripple", "XRP", "XRP", "https://assets.coingecko.com/coins/images/44/large/xrp-symbol-white-128.png"),
        "ADAUSDT": ("cardano", "ADA", "Cardano", "https://assets.coingecko.com/coins/images/975/large/cardano.png"),
        "DOGEUSDT": ("dogecoin", "DOGE", "Dogecoin", "https://assets.coingecko.com/coins/images/5/large/dogecoin.png"),
        "AVAXUSDT": ("avalanche-2", "AVAX", "Avalanche", "https://assets.coingecko.com/coins/images/12559/large/Avalanche_Circle_RedWhite_Trans.png"),
        "LINKUSDT": ("chainlink", "LINK", "Chainlink", "https://assets.coingecko.com/coins/images/877/large/chainlink-new-logo.png"),
        "TRXUSDT": ("tron", "TRX", "TRON", "https://assets.coingecko.com/coins/images/1094/large/tron-logo.png"),
    }

    try:
        data = get_json("https://api.binance.com/api/v3/ticker/24hr", timeout=8)
        by_symbol = {item.get("symbol"): item for item in data}

        result = []

        for binance_symbol, coin_data in symbols.items():
            item = by_symbol.get(binance_symbol)
            if not item:
                continue

            coin_id, symbol, name, image = coin_data
            price = safe_float(item.get("lastPrice"))
            change_24h = safe_float(item.get("priceChangePercent"))
            volume = safe_float(item.get("quoteVolume"))

            result.append({
                "id": coin_id,
                "symbol": symbol,
                "name": name,
                "image": image,
                "price": price,
                "price_display": f"${price:,.4f}",
                "market_cap": 0,
                "market_cap_display": "Live price",
                "volume": volume,
                "volume_display": money_short(volume),
                "change_24h": change_24h,
                "change_7d": 0.0,
                "bar_width": 30,
                "sparkline": [],
            })

        if result:
            _LAST_GOOD["markets"] = result
            return result

    except Exception as e:
        print("BINANCE BACKUP ERROR:", e)

    return fallback_markets()


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
                "price_change_percentage": "24h,7d",
            },
            timeout=10,
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

        return load_markets_from_binance()

    except Exception as e:
        print("COINGECKO MARKETS ERROR:", e)
        return load_markets_from_binance()


def load_trending():
    try:
        data = get_json("https://api.coingecko.com/api/v3/search/trending", timeout=8)
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

    return fallback_trending()


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
                timeout=8,
                headers={"User-Agent": "VelWolfSignals/1.0"},
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

    return fallback_news()


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

        item = dict(coin)
        item["reason"] = reason
        smart.append(item)

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

    for item in news:
        symbol = (item.get("coin") or "").upper()
        if symbol and symbol != "MARKET":
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

    data_status = "live"
    if not markets:
        data_status = "unavailable"

    return {
        "global_market": global_market,
        "markets": markets,
        "trending": trending,
        "news": news,
        "summary": summary,
        "smart_watchlist": smart_watchlist,
        "watchlist_access": user_has_watchlist_access(current_user),
        "updated_at": datetime.now(timezone.utc).strftime("%H:%M UTC"),
        "data_status": data_status,
    }


def get_cached_data():
    now = time.time()

    if _CACHE["data"] and now - _CACHE["ts"] < CACHE_SECONDS:
        data = dict(_CACHE["data"])
        data["watchlist_access"] = user_has_watchlist_access(current_user)
        return data

    try:
        data = build_page_data()

        if data.get("markets") or data.get("news"):
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
            data["data_status"] = "cached"
            return data

        markets = fallback_markets()
        news = fallback_news()
        summary = build_summary(markets, news)

        return {
            "global_market": fallback_global_market(),
            "markets": markets,
            "trending": fallback_trending(),
            "news": news,
            "summary": summary,
            "smart_watchlist": build_smart_watchlist(markets, news),
            "watchlist_access": user_has_watchlist_access(current_user),
            "updated_at": datetime.now(timezone.utc).strftime("%H:%M UTC"),
            "data_status": "unavailable",
        }


@news_feed_bp.route("/news-feed")
def news_feed_default():
    return redirect(url_for("news_feed.news_feed", lang_code="fr"))


@news_feed_bp.route("/<lang_code>/news-feed")
def news_feed(lang_code="fr"):
    if lang_code not in SUPPORTED_LANGS:
        return redirect(url_for("news_feed.news_feed", lang_code="fr"))

    data = get_cached_data()
    return render_template("news_feed.html", **data, lang_code=lang_code)


@news_feed_bp.route("/api/news-feed")
def news_feed_api_default():
    return redirect(url_for("news_feed.news_feed_api", lang_code="fr"))


@news_feed_bp.route("/<lang_code>/api/news-feed")
def news_feed_api(lang_code="fr"):
    if lang_code not in SUPPORTED_LANGS:
        lang_code = "fr"

    data = get_cached_data()
    data["lang_code"] = lang_code
    return jsonify(data)