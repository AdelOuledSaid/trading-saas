import requests
from flask import current_app
import config
from app.extensions import cache


NEWS_BACKUP_CACHE_KEY = "market_updates_backup_v1"
CRYPTO_LIVE_BACKUP_KEY = "crypto_live_backup_v2"
GLOBAL_MARKET_BACKUP_KEY = "global_market_backup_v2"
FEAR_GREED_BACKUP_KEY = "fear_greed_backup_v2"


def coingecko_headers():
    headers = {
        "accept": "application/json",
        "User-Agent": "VelWolf/1.0"
    }
    api_key = getattr(config, "COINGECKO_API_KEY", None)
    if api_key:
        headers["x-cg-pro-api-key"] = api_key
    return headers


def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


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


def format_currency(value, decimals=0):
    try:
        value = float(value)
    except Exception:
        return "..."
    return f"${value:,.{decimals}f}"


def get_btc_data():
    crypto = get_crypto_market_live("bitcoin")
    btc = crypto.get("bitcoin", {})

    price = safe_float(btc.get("usd"))
    change = safe_float(btc.get("usd_24h_change"))

    if not price:
        raise ValueError("Prix BTC introuvable")

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


@cache.memoize(timeout=600)
def get_crypto_market_live(ids="bitcoin,ethereum"):
    """
    Cache 10 minutes pour éviter les erreurs CoinGecko 429.
    Si CoinGecko bloque, on retourne la dernière donnée valide.
    """
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": ids,
        "vs_currencies": "usd",
        "include_market_cap": "true",
        "include_24hr_vol": "true",
        "include_24hr_change": "true",
        "include_last_updated_at": "true",
    }

    backup_key = f"{CRYPTO_LIVE_BACKUP_KEY}:{ids}"

    try:
        response = requests.get(
            url,
            params=params,
            headers=coingecko_headers(),
            timeout=12
        )
        response.raise_for_status()
        data = response.json()

        if data:
            cache.set(backup_key, data, timeout=3600)

        return data or {}

    except Exception as e:
        current_app.logger.warning("CoinGecko crypto fallback utilisé: %s", repr(e))
        cached = cache.get(backup_key)
        return cached or {}


@cache.memoize(timeout=900)
def get_global_market_live():
    """
    Cache 15 minutes.
    Cette fonction donne déjà btc_dominance, donc on évite un deuxième appel /global ailleurs.
    """
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/global",
            headers=coingecko_headers(),
            timeout=12
        )
        r.raise_for_status()
        data = r.json().get("data", {})

        result = {
            "market_cap_usd": safe_float(data.get("total_market_cap", {}).get("usd")),
            "volume_usd": safe_float(data.get("total_volume", {}).get("usd")),
            "btc_dominance": safe_float(data.get("market_cap_percentage", {}).get("btc")),
            "active_cryptos": data.get("active_cryptocurrencies", 0),
            "markets": data.get("markets", 0),
            "market_cap_change_24h": safe_float(data.get("market_cap_change_percentage_24h_usd")),
        }

        cache.set(GLOBAL_MARKET_BACKUP_KEY, result, timeout=3600)
        return result

    except Exception as e:
        current_app.logger.warning("CoinGecko global fallback utilisé: %s", repr(e))
        cached = cache.get(GLOBAL_MARKET_BACKUP_KEY)

        if cached:
            return cached

        return {
            "market_cap_usd": 0,
            "volume_usd": 0,
            "btc_dominance": 0,
            "active_cryptos": 0,
            "markets": 0,
            "market_cap_change_24h": 0,
        }


@cache.memoize(timeout=900)
def get_btc_dominance_live():
    """
    Gardée pour compatibilité, mais utilise get_global_market_live()
    pour éviter un appel CoinGecko supplémentaire.
    """
    global_data = get_global_market_live()
    return round(safe_float(global_data.get("btc_dominance")), 2)


@cache.memoize(timeout=900)
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

    except Exception:
        cached = cache.get(FEAR_GREED_BACKUP_KEY)
        return cached or {"value": 50, "classification": "Neutral"}


@cache.memoize(timeout=900)
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
        current_app.logger.warning("Erreur news asset fallback: %s", repr(e))
        return []


def compute_sentiment_score(change_btc, change_eth, btc_dominance, fear_value):
    score = 50

    if change_btc >= 3:
        score += 15
    elif change_btc >= 1:
        score += 10
    elif change_btc > 0:
        score += 5
    elif change_btc <= -3:
        score -= 15
    elif change_btc <= -1:
        score -= 10
    elif change_btc < 0:
        score -= 5

    if change_eth >= 4:
        score += 12
    elif change_eth >= 1.5:
        score += 8
    elif change_eth > 0:
        score += 4
    elif change_eth <= -4:
        score -= 12
    elif change_eth <= -1.5:
        score -= 8
    elif change_eth < 0:
        score -= 4

    if btc_dominance >= 54:
        score += 6
    elif btc_dominance >= 50:
        score += 3
    elif btc_dominance < 48:
        score -= 4

    if 55 <= fear_value <= 75:
        score += 8
    elif 45 <= fear_value < 55:
        score += 3
    elif 25 <= fear_value < 45:
        score -= 5
    elif fear_value < 25:
        score -= 12
    elif fear_value > 85:
        score -= 6

    return max(0, min(100, int(round(score))))


def compute_market_regime_from_score(score):
    if score >= 72:
        return "Expansion"
    if score >= 58:
        return "Rotation"
    if score >= 42:
        return "Compression"
    return "Breakdown Risk"


def compute_market_bias_from_score(score):
    if score >= 72:
        return "Risk-On"
    if score >= 60:
        return "Bullish"
    if score >= 52:
        return "Positive"
    if score >= 42:
        return "Neutral"
    if score >= 30:
        return "Defensive"
    return "Risk-Off"


def compute_ai_confidence_from_score(score):
    if score >= 80:
        return 88
    if score >= 72:
        return 80
    if score >= 60:
        return 72
    if score >= 52:
        return 64
    if score >= 42:
        return 55
    if score >= 30:
        return 44
    return 34


def compute_ai_confidence_explanation_from_score(score):
    if score >= 80:
        return "Contexte très propre : tendance, momentum et flux sont alignés."
    if score >= 72:
        return "Contexte favorable : structure haussière et appétit risque soutiennent le scénario."
    if score >= 60:
        return "Confiance constructive : biais positif, mais sélectivité encore nécessaire."
    if score >= 52:
        return "Confiance modérée : avantage léger, sans domination complète du contexte."
    if score >= 42:
        return "Contexte neutre : marché en attente, patience recommandée."
    if score >= 30:
        return "Confiance faible : structure fragile, prudence avant engagement."
    return "Confiance très faible : risque élevé d'invalidation et contexte défensif."


def compute_bias_principal_from_score(score):
    if score >= 72:
        return "Continuation haussière sous surveillance"
    if score >= 58:
        return "Rotation active sous contrôle"
    if score >= 42:
        return "Compression, patience requise"
    return "Risque baissier / défensif"


def compute_dominance_label(btc_dominance):
    if btc_dominance >= 52:
        return "Capital Lead"
    if btc_dominance >= 49:
        return "Balanced"
    return "Altcoin Rotation"


def compute_altcoin_appetite(change_eth, change_btc):
    if change_eth > 2 and change_eth >= change_btc:
        return "Aggressive"
    if change_eth > 0:
        return "Selective"
    return "Weak"


def compute_macro_pressure(fear_value, change_btc):
    if fear_value < 35 or change_btc < -2:
        return "Elevated"
    if fear_value > 65 and change_btc > 0:
        return "Contained"
    return "Monitored"


def compute_execution_mode(regime):
    if regime == "Expansion":
        return "Trend Following"
    if regime == "Rotation":
        return "Selective Rotation"
    if regime == "Compression":
        return "Patience"
    return "Defense First"


@cache.memoize(timeout=600)
def get_market_overview():
    crypto = get_crypto_market_live("bitcoin,ethereum")
    fear = get_fear_greed_live()
    global_data = get_global_market_live()

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

    btc_dom_value = safe_float(global_data.get("btc_dominance"))
    sentiment_score = compute_sentiment_score(btc_change, eth_change, btc_dom_value, fear_value)
    bias = compute_market_bias_from_score(sentiment_score)

    return {
        "hero": {
            "market_bias": bias,
            "fear_greed_value": fear_value,
            "fear_greed_label": fear.get("classification", "Neutral"),
            "btc_dominance": round(btc_dom_value, 2),
            "sentiment_score": sentiment_score,
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


@cache.memoize(timeout=600)
def get_crypto_command_center():
    crypto = get_crypto_market_live("bitcoin,ethereum")
    fear = get_fear_greed_live()
    global_data = get_global_market_live()

    btc = crypto.get("bitcoin", {})
    eth = crypto.get("ethereum", {})

    btc_price = safe_float(btc.get("usd"))
    eth_price = safe_float(eth.get("usd"))
    btc_change = safe_float(btc.get("usd_24h_change"))
    eth_change = safe_float(eth.get("usd_24h_change"))
    btc_market_cap = safe_float(btc.get("usd_market_cap"))
    eth_market_cap = safe_float(eth.get("usd_market_cap"))

    fear_raw = fear.get("value", 50)
    try:
        fear_value = int(fear_raw)
    except Exception:
        fear_value = 50

    btc_dominance = safe_float(global_data.get("btc_dominance"))
    total_market_cap = safe_float(global_data.get("market_cap_usd"))
    total_volume = safe_float(global_data.get("volume_usd"))

    sentiment_score = compute_sentiment_score(
        btc_change,
        eth_change,
        btc_dominance,
        fear_value
    )

    market_regime = compute_market_regime_from_score(sentiment_score)
    risk_mode = compute_market_bias_from_score(sentiment_score)
    ai_confidence = compute_ai_confidence_from_score(sentiment_score)
    ai_confidence_explanation = compute_ai_confidence_explanation_from_score(sentiment_score)

    dominance_label = compute_dominance_label(btc_dominance)
    altcoin_appetite = compute_altcoin_appetite(eth_change, btc_change)
    macro_pressure = compute_macro_pressure(fear_value, btc_change)
    execution_mode = compute_execution_mode(market_regime)
    bias_principal = compute_bias_principal_from_score(sentiment_score)

    if market_regime == "Expansion":
        main_scenario = "Continuation haussière si la structure BTC reste propre"
        invalidation = "Perte de momentum BTC + chute de la dominance + dégradation du sentiment"
        rotation_text = "BTC mène, ETH suit, puis alts sélectives"
        desk_priority = "Suivi de tendance sur actifs leaders"
        momentum_label = "Strong" if btc_change > 2 else "Stable"
        dominance_state = "Positive" if btc_dominance >= 50 else "Neutral"
        macro_state = "Supportive" if fear_value >= 55 else "Mixed"
        execution_state = "Aggressive" if risk_mode in ("Risk-On", "Bullish") else "Selective"

    elif market_regime == "Rotation":
        main_scenario = "Rotation progressive du capital vers ETH et certaines altcoins"
        invalidation = "Reprise forte de la dominance BTC ou faiblesse rapide d'ETH"
        rotation_text = "ETH et alts reprennent du terrain face à BTC"
        desk_priority = "Sélection des rotations les plus propres"
        momentum_label = "Rotational"
        dominance_state = "Neutral"
        macro_state = "Mixed"
        execution_state = "Selective"

    elif market_regime == "Compression":
        main_scenario = "Marché en attente d'un déclencheur directionnel clair"
        invalidation = "Cassure de range avec volume et suivi"
        rotation_text = "Pas de rotation claire, marché encore hésitant"
        desk_priority = "Contexte avant breakout"
        momentum_label = "Muted"
        dominance_state = "Balanced"
        macro_state = "Monitored"
        execution_state = "Patience"

    else:
        main_scenario = "Risque de dégradation structurelle, prudence maximale"
        invalidation = "Réintégration haussière des niveaux clés avec reprise du sentiment"
        rotation_text = "Capital défensif, peu d'appétit pour les altcoins"
        desk_priority = "Préservation du capital"
        momentum_label = "Weak"
        dominance_state = "Fragile"
        macro_state = "Elevated"
        execution_state = "Defense"

    watchlist = [
        {
            "name": "Bitcoin",
            "score": 9.4 if btc_change >= 0 else 8.7,
            "description": "Leader du marché, repère principal pour la direction globale et la qualité des impulsions.",
            "tag_1": "Leader",
            "tag_2": "High Priority",
            "css_class": "high",
        },
        {
            "name": "Ethereum",
            "score": 8.8 if eth_change >= 0 else 8.1,
            "description": "Actif de transition clé pour lire la rotation du capital et le comportement altcoin.",
            "tag_1": "Rotation Watch",
            "tag_2": "High Priority",
            "css_class": "high",
        },
        {
            "name": "Solana",
            "score": 7.9,
            "description": "Momentum spéculatif élevé, utile pour mesurer l’appétit au risque du marché.",
            "tag_1": "Momentum",
            "tag_2": "Selective",
            "css_class": "",
        },
        {
            "name": "Total Market Cap",
            "score": 9.1 if total_market_cap > 0 else 8.5,
            "description": "Vue macro indispensable pour confirmer la force globale du marché et valider les scénarios.",
            "tag_1": "Macro",
            "tag_2": "High Priority",
            "css_class": "macro",
        },
    ]

    return {
        "btc_price": format_currency(btc_price, 0),
        "eth_price": format_currency(eth_price, 0),
        "btc_change_24h": round(btc_change, 2),
        "eth_change_24h": round(eth_change, 2),
        "btc_dominance": round(btc_dominance, 2),
        "total_market_cap": format_big_number(total_market_cap),
        "total_volume": format_big_number(total_volume),
        "fear_greed_value": fear_value,
        "fear_greed_label": fear.get("classification", "Neutral"),
        "sentiment_score": sentiment_score,
        "risk_mode": risk_mode,
        "market_regime": market_regime,
        "dominance_label": dominance_label,
        "altcoin_appetite": altcoin_appetite,
        "macro_pressure": macro_pressure,
        "execution_mode": execution_mode,
        "main_scenario": main_scenario,
        "invalidation": invalidation,
        "assets_focus": "BTC / ETH / TOTAL / BTC.D",
        "desk_mode": execution_mode,
        "bias_principal": bias_principal,
        "rotation_text": rotation_text,
        "desk_priority": desk_priority,
        "momentum_label": momentum_label,
        "dominance_state": dominance_state,
        "macro_state": macro_state,
        "execution_state": execution_state,
        "btc_market_cap": format_big_number(btc_market_cap) if btc_market_cap else "-",
        "eth_market_cap": format_big_number(eth_market_cap) if eth_market_cap else "-",
        "watchlist": watchlist,
        "ai_confidence": ai_confidence,
        "ai_confidence_explanation": ai_confidence_explanation,
    }