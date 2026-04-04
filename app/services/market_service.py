import requests
from flask import current_app
import config
from app.extensions import cache


def get_btc_data():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "ids": "bitcoin",
        "price_change_percentage": "24h",
    }

    response = requests.get(url, params=params, timeout=10)
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

    return f"""
Prix actuel : {price} USD
Variation 24h : {round(change, 2)}%
Tendance court terme : {trend}
Support : {support}
Résistance : {resistance}
Volume : élevé
Momentum : {"positif" if change > 0 else "négatif" if change < 0 else "neutre"}
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


def get_market_updates():
    if not config.NEWS_API_KEY:
        current_app.logger.warning("NEWS_API_KEY manquante. Market Updates vide.")
        return []

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

        return articles[:6]

    except Exception as e:
        current_app.logger.error("Erreur récupération Market Updates: %s", repr(e))
        return []


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


@cache.memoize(timeout=120)
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

    try:
        response = requests.get(url, params=params, headers=coingecko_headers(), timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        current_app.logger.error("Erreur crypto live: %s", repr(e))
        return {}


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
        data = r.json()["data"][0]
        return {
            "value": data["value"],
            "classification": data["value_classification"]
        }
    except Exception:
        return {"value": "...", "classification": "..."}


@cache.memoize(timeout=300)
def get_btc_dominance_live():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/global", timeout=10)
        data = r.json()["data"]
        return round(data["market_cap_percentage"]["btc"], 2)
    except Exception:
        return "..."