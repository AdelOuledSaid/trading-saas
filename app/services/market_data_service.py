import requests
from flask import current_app
import config
from app.extensions import cache


NEWS_BACKUP_CACHE_KEY = "market_updates_backup_v1"
CRYPTO_LIVE_BACKUP_PREFIX = "crypto_live_backup"
BTC_DOM_BACKUP_KEY = "btc_dominance_backup_v1"
FEAR_GREED_BACKUP_KEY = "fear_greed_backup_v1"
MARKET_OVERVIEW_BACKUP_KEY = "market_overview_backup_v1"
BTC_DATA_BACKUP_KEY = "btc_data_backup_v1"


def coingecko_headers():
    headers = {"accept": "application/json"}
    if config.COINGECKO_API_KEY:
        headers["x-cg-pro-api-key"] = config.COINGECKO_API_KEY
    return headers


def format_big_number(value):
    try:
        value = float(value)
    except Exception:
        return "..."

    if value >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:.2f}T"
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value / 1_000:.2f}K"
    return f"{value:.2f}"


def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def compute_market_bias(change_btc, change_eth, btc_dominance, fear_value):
    score = 0

    if change_btc > 0:
        score += 1
    elif change_btc < 0:
        score -= 1

    if change_eth > 0:
        score += 1
    elif change_eth < 0:
        score -= 1

    if btc_dominance >= 55:
        score += 1
    elif btc_dominance < 50:
        score -= 1

    if fear_value >= 60:
        score += 1
    elif fear_value <= 40:
        score -= 1

    if score >= 3:
        return "Risk-On"
    if score == 2:
        return "Bullish"
    if score == 1:
        return "Positive"
    if score == 0:
        return "Neutral"
    if score <= -3:
        return "Risk-Off"
    return "Defensive"


@cache.memoize(timeout=180)
def get_btc_data():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "ids": "bitcoin",
        "price_change_percentage": "24h",
    }

    try:
        response = requests.get(url, params=params, headers=coingecko_headers(), timeout=15)
        response.raise_for_status()
        data = response.json()

        if not data:
            raise ValueError("Aucune donnée BTC reçue")

        btc = data[0]

        price = btc.get("current_price")
        change = btc.get("price_change_percentage_24h_in_currency")

        if price is None:
            raise ValueError("Prix BTC introuvable")

        if change is None:
            change = 0

        trend = "haussière" if change > 0 else "baissière" if change < 0 else "neutre"

        support = round(price * 0.99, 2)
        resistance = round(price * 1.01, 2)

        result = f"""
Prix actuel : {price} USD
Variation 24h : {round(change, 2)}%
Tendance court terme : {trend}
Support : {support}
Résistance : {resistance}
Volume : élevé
Momentum : {"positif" if change > 0 else "négatif" if change < 0 else "neutre"}
""".strip()

        cache.set(BTC_DATA_BACKUP_KEY, result, timeout=3600)
        return result

    except Exception as e:
        current_app.logger.warning("Fallback BTC data utilisé: %s", repr(e))
        cached = cache.get(BTC_DATA_BACKUP_KEY)
        if cached:
            return cached

        return """
Prix actuel : ...
Variation 24h : ...
Tendance court terme : neutre
Support : ...
Résistance : ...
Volume : ...
Momentum : ...
""".strip()


def get_gold_data():
    price = 3085

    return f"""
Prix actuel : {price} USD
Variation 24h : -0.3%
Tendance court terme : neutre à baissière
Support : 3068
Résistance : 3100
Contexte : marché en attente des données macro
""".strip()


def get_economic_calendar():
    return """
- 14:30 : Inflation CPI USA (impact fort)
- 16:00 : Confiance consommateurs (impact moyen)
- 20:00 : Discours FED (impact fort)

Contexte global :
Marché attentif à l'inflation et aux taux.
Risque de forte volatilité aujourd’hui.
""".strip()


@cache.memoize(timeout=900)
def get_market_updates():
    if not config.NEWS_API_KEY:
        current_app.logger.warning("NEWS_API_KEY manquante. Market Updates vide.")
        cached = cache.get(NEWS_BACKUP_CACHE_KEY)
        return cached or []

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": '(bitcoin OR btc OR ethereum OR eth OR gold OR "nasdaq" OR "us100" OR crypto)',
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 6,
        "apiKey": config.NEWS_API_KEY,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        articles = []
        for article in data.get("articles", []):
            image_url = article.get("urlToImage")
            title = article.get("title")
            source = (article.get("source") or {}).get("name", "Source")
            article_url = article.get("url")
            description = article.get("description") or ""

            if not title or not article_url:
                continue

            articles.append({
                "title": title,
                "description": description,
                "image": image_url,
                "source": source,
                "url": article_url,
            })

        articles = articles[:6]
        cache.set(NEWS_BACKUP_CACHE_KEY, articles, timeout=3600)
        return articles

    except Exception as e:
        current_app.logger.warning("Market Updates fallback utilisé: %s", repr(e))
        cached = cache.get(NEWS_BACKUP_CACHE_KEY)
        return cached or []


@cache.memoize(timeout=180)
def get_crypto_market_live(ids="bitcoin,ethereum"):
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": ids,
        "vs_currencies": "usd",
        "include_market_cap": "true",
        "include_24hr_vol": "true",
        "include_24hr_change": "true",
        "include_last_updated_at": "true",
    }

    backup_key = f"{CRYPTO_LIVE_BACKUP_PREFIX}:{ids}"

    try:
        response = requests.get(url, params=params, headers=coingecko_headers(), timeout=15)
        response.raise_for_status()
        data = response.json()
        cache.set(backup_key, data, timeout=1800)
        return data
    except Exception as e:
        current_app.logger.error("Erreur crypto live: %s", repr(e))
        cached = cache.get(backup_key)
        return cached or {}


@cache.memoize(timeout=600)
def get_asset_news(asset_key, limit=6):
    if not config.NEWS_API_KEY:
        return []

    queries = {
        "BTC": '(bitcoin OR btc)',
        "ETH": '(ethereum OR eth)',
    }

    q = queries.get(asset_key.upper())
    if not q:
        return []

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": q,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": limit,
        "apiKey": config.NEWS_API_KEY,
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        articles = []
        for a in data.get("articles", []):
            if not a.get("title") or not a.get("url"):
                continue

            articles.append({
                "title": a["title"],
                "description": a.get("description", ""),
                "image": a.get("urlToImage"),
                "source": a.get("source", {}).get("name", "Source"),
                "url": a["url"],
            })

        return articles[:limit]

    except Exception as e:
        current_app.logger.error("Erreur news: %s", repr(e))
        return []


@cache.memoize(timeout=300)
def get_fear_greed_live():
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        r.raise_for_status()
        data = r.json()["data"][0]

        result = {
            "value": data["value"],
            "classification": data["value_classification"]
        }
        cache.set(FEAR_GREED_BACKUP_KEY, result, timeout=3600)
        return result

    except Exception as e:
        current_app.logger.warning("Fear & Greed fallback utilisé: %s", repr(e))
        cached = cache.get(FEAR_GREED_BACKUP_KEY)
        return cached or {"value": "...", "classification": "..."}


@cache.memoize(timeout=300)
def get_btc_dominance_live():
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/global",
            headers=coingecko_headers(),
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()["data"]
        result = round(data["market_cap_percentage"]["btc"], 2)
        cache.set(BTC_DOM_BACKUP_KEY, result, timeout=3600)
        return result

    except Exception as e:
        current_app.logger.warning("BTC dominance fallback utilisé: %s", repr(e))
        cached = cache.get(BTC_DOM_BACKUP_KEY)
        return cached if cached is not None else "..."


@cache.memoize(timeout=300)
def get_market_overview():
    try:
        crypto = get_crypto_market_live("bitcoin,ethereum")
        fear = get_fear_greed_live()
        btc_dominance = get_btc_dominance_live()

        btc = crypto.get("bitcoin", {})
        eth = crypto.get("ethereum", {})

        btc_price = safe_float(btc.get("usd"))
        eth_price = safe_float(eth.get("usd"))
        btc_change = safe_float(btc.get("usd_24h_change"))
        eth_change = safe_float(eth.get("usd_24h_change"))
        btc_cap = btc.get("usd_market_cap")
        eth_cap = eth.get("usd_market_cap")

        fear_raw = fear.get("value", 50)
        try:
            fear_value = int(fear_raw)
        except Exception:
            fear_value = 50

        btc_dom_value = safe_float(btc_dominance)

        bias = compute_market_bias(btc_change, eth_change, btc_dom_value, fear_value)

        result = {
            "hero": {
                "market_bias": bias,
                "fear_greed_value": fear_value,
                "fear_greed_label": fear.get("classification", "Neutral"),
                "btc_dominance": round(btc_dom_value, 2),
            },
            "assets": [
                {
                    "symbol": "BTC",
                    "name": "Bitcoin",
                    "price": round(btc_price, 2) if btc_price else 0,
                    "change_24h": round(btc_change, 2),
                    "market_cap": format_big_number(btc_cap) if btc_cap else "-",
                },
                {
                    "symbol": "ETH",
                    "name": "Ethereum",
                    "price": round(eth_price, 2) if eth_price else 0,
                    "change_24h": round(eth_change, 2),
                    "market_cap": format_big_number(eth_cap) if eth_cap else "-",
                },
                {
                    "symbol": "BTC.D",
                    "name": "BTC Dominance",
                    "price": round(btc_dom_value, 2),
                    "change_24h": None,
                    "market_cap": "-",
                },
                {
                    "symbol": "F&G",
                    "name": "Fear & Greed",
                    "price": fear_value,
                    "change_24h": None,
                    "market_cap": fear.get("classification", "Neutral"),
                },
            ]
        }

        cache.set(MARKET_OVERVIEW_BACKUP_KEY, result, timeout=3600)
        return result

    except Exception as e:
        current_app.logger.warning("Market overview fallback utilisé: %s", repr(e))
        cached = cache.get(MARKET_OVERVIEW_BACKUP_KEY)
        if cached:
            return cached

        return {
            "hero": {
                "market_bias": "Neutral",
                "fear_greed_value": 50,
                "fear_greed_label": "Neutral",
                "btc_dominance": 0,
            },
            "assets": [
                {
                    "symbol": "BTC",
                    "name": "Bitcoin",
                    "price": 0,
                    "change_24h": 0,
                    "market_cap": "-",
                },
                {
                    "symbol": "ETH",
                    "name": "Ethereum",
                    "price": 0,
                    "change_24h": 0,
                    "market_cap": "-",
                },
                {
                    "symbol": "BTC.D",
                    "name": "BTC Dominance",
                    "price": 0,
                    "change_24h": None,
                    "market_cap": "-",
                },
                {
                    "symbol": "F&G",
                    "name": "Fear & Greed",
                    "price": 50,
                    "change_24h": None,
                    "market_cap": "Neutral",
                },
            ]
        }