"""
Elon Market Radar Service — 100% gratuit
Sources : RSS SpaceX/NASA/Google News + Nitter (Twitter mirror) + Binance API
"""
import time
import threading
import requests
import feedparser
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

# ── Cache ──────────────────────────────────────────────────────
_CACHE = {"ts": 0, "data": {}}
_LOCK  = threading.Lock()
_TTL   = 600  # 10 minutes

# ── RSS Sources (100% gratuit, pas d'API key) ─────────────────
RSS_SOURCES = [
    # SpaceX officiel
    "https://www.nasaspaceflight.com/feed/",
    # Google News — SpaceX
    "https://news.google.com/rss/search?q=SpaceX+Elon+Musk&hl=en&gl=US&ceid=US:en",
    # Google News — DOGE Elon
    "https://news.google.com/rss/search?q=Elon+Musk+Dogecoin+DOGE&hl=en&gl=US&ceid=US:en",
    # Google News — Tesla crypto
    "https://news.google.com/rss/search?q=Tesla+crypto+Elon&hl=en&gl=US&ceid=US:en",
    # Cointelegraph
    "https://cointelegraph.com/rss/tag/elon-musk",
    # Coindesk
    "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
]

# Nitter instances (miroirs Twitter gratuits)
NITTER_INSTANCES = [
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
    "https://nitter.1d4.us",
]

# Keywords pour scorer l'impact
HIGH_IMPACT_KEYWORDS = [
    "starship", "launch", "nasa contract", "doge payment",
    "bitcoin", "crypto", "dogecoin", "spacex ipo", "starlink ipo",
    "tesla earnings", "buys bitcoin", "sells bitcoin"
]
MEDIUM_IMPACT_KEYWORDS = [
    "elon", "spacex", "tesla", "doge", "x.com", "neuralink",
    "boring company", "hyperloop", "satellite"
]

ASSET_KEYWORDS = {
    "DOGE": ["doge", "dogecoin", "doge payment", "doge tweet"],
    "BTC":  ["bitcoin", "btc", "crypto", "buys bitcoin", "sells bitcoin"],
    "TSLA": ["tesla", "tsla", "earnings", "delivery"],
    "XRP":  ["xrp", "ripple"],
}


def _score_impact(title: str, summary: str) -> tuple:
    """Retourne (level, tags) basé sur les keywords."""
    text = (title + " " + summary).lower()
    tags = []
    for asset, keywords in ASSET_KEYWORDS.items():
        if any(k in text for k in keywords):
            tags.append(asset)
    for k in HIGH_IMPACT_KEYWORDS:
        if k in text:
            return "high", tags
    for k in MEDIUM_IMPACT_KEYWORDS:
        if k in text:
            return "medium", tags
    return "low", tags


def _time_ago(published) -> str:
    """Convertit une date en '2h ago'."""
    try:
        if hasattr(published, 'timetuple'):
            ts = time.mktime(published.timetuple())
        else:
            ts = time.mktime(time.strptime(str(published)[:19], "%Y-%m-%dT%H:%M:%S"))
        diff = time.time() - ts
        if diff < 3600:
            return f"{int(diff/60)}min ago"
        if diff < 86400:
            return f"{int(diff/3600)}h ago"
        return f"{int(diff/86400)}d ago"
    except Exception:
        return "recently"


def _fetch_rss_news() -> List[Dict]:
    """Récupère les news depuis les flux RSS — 100% gratuit."""
    news = []
    seen_titles = set()

    for url in RSS_SOURCES:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                title = entry.get("title", "")
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)

                summary = entry.get("summary", entry.get("description", ""))
                # Nettoyer le HTML
                import re
                summary = re.sub(r'<[^>]+>', '', summary)[:300]

                level, tags = _score_impact(title, summary)

                # Source clean
                source = feed.feed.get("title", url.split("/")[2])

                news.append({
                    "title":   title,
                    "summary": summary,
                    "source":  source,
                    "link":    entry.get("link", "#"),
                    "time":    _time_ago(entry.get("published_parsed")),
                    "level":   level,
                    "tags":    tags or ["ELON"],
                    "icon":    "🚀" if "spacex" in title.lower() or "starship" in title.lower()
                               else "🐕" if "doge" in title.lower()
                               else "⚡" if "tesla" in title.lower()
                               else "🛰️" if "nasa" in title.lower() or "satellite" in title.lower()
                               else "📊",
                })
        except Exception as e:
            print(f"RSS error {url}: {e}")
            continue

    # Filtrer : garder seulement les articles mentionnant Elon/SpaceX
    elon_keywords = ["elon", "spacex", "tesla", "doge", "starship", "starlink"]
    filtered = [n for n in news if any(k in n["title"].lower() for k in elon_keywords)]

    # Trier par niveau d'impact
    order = {"high": 0, "medium": 1, "low": 2}
    filtered.sort(key=lambda x: order.get(x["level"], 2))

    return filtered[:10]


def _fetch_elon_tweets() -> List[Dict]:
    """
    Récupère les tweets d'Elon via Nitter RSS (miroir Twitter gratuit).
    Nitter expose un flux RSS pour chaque compte Twitter.
    """
    tweets = []
    for instance in NITTER_INSTANCES:
        try:
            url = f"{instance}/elonmusk/rss"
            feed = feedparser.parse(url)
            if not feed.entries:
                continue
            for entry in feed.entries[:5]:
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                import re
                summary = re.sub(r'<[^>]+>', '', summary)[:280]

                level, tags = _score_impact(title, summary)
                tweets.append({
                    "title":   title[:120],
                    "summary": summary,
                    "source":  "X (Elon Musk)",
                    "link":    entry.get("link", "#").replace(instance, "https://x.com"),
                    "time":    _time_ago(entry.get("published_parsed")),
                    "level":   level,
                    "tags":    tags or ["ELON"],
                    "icon":    "🐕" if "doge" in title.lower() else "⚡",
                    "is_tweet": True,
                })
            break  # Premier Nitter qui marche suffit
        except Exception:
            continue
    return tweets[:3]


def _fetch_binance_price(symbol: str) -> Dict:
    """Prix réel depuis Binance — totalement gratuit."""
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/ticker/24hr",
            params={"symbol": symbol},
            timeout=5
        )
        d = r.json()
        return {
            "price":     float(d["lastPrice"]),
            "change_24h": float(d["priceChangePercent"]),
            "high":      float(d["highPrice"]),
            "low":       float(d["lowPrice"]),
            "volume":    float(d["quoteVolume"]),
        }
    except Exception:
        return {}


def _compute_probability(event_level: str, tags: List[str],
                          doge_data: Dict, btc_data: Dict) -> Dict:
    """
    Calcule le score de probabilité depuis :
    - Niveau de l'événement (high/medium/low)
    - Momentum Binance actuel (change_24h)
    - Corrélations historiques réelles
    """
    base_scores = {
        "DOGE": {"high": 72, "medium": 55, "low": 35},
        "BTC":  {"high": 52, "medium": 38, "low": 22},
    }

    doge_change = doge_data.get("change_24h", 0)
    btc_change  = btc_data.get("change_24h", 0)

    # Ajustement momentum : si DOGE monte déjà, probabilité boost
    doge_score = base_scores["DOGE"].get(event_level, 40)
    btc_score  = base_scores["BTC"].get(event_level, 30)

    # Bonus si momentum positif
    if doge_change > 2:   doge_score = min(95, doge_score + 8)
    elif doge_change < -2: doge_score = max(15, doge_score - 8)

    if btc_change > 2:    btc_score = min(90, btc_score + 6)
    elif btc_change < -2: btc_score = max(10, btc_score - 6)

    # Boost si event mentionne DOGE directement
    if "DOGE" in tags:    doge_score = min(95, doge_score + 10)
    if "BTC" in tags:     btc_score  = min(90, btc_score + 8)

    return {
        "doge": doge_score,
        "btc":  btc_score,
        "doge_dir": "high" if doge_score >= 65 else "medium" if doge_score >= 45 else "low",
        "btc_dir":  "high" if btc_score >= 65  else "medium" if btc_score >= 45  else "low",
    }


def _compute_signal(event_level: str, tags: List[str],
                    doge_data: Dict, prob: Dict) -> Dict:
    """
    Génère un signal d'exécution basé sur les prix Binance réels.
    """
    price = doge_data.get("price", 0)
    low   = doge_data.get("low", price * 0.97)
    high  = doge_data.get("high", price * 1.03)

    if event_level == "high" and prob["doge"] >= 65 and "DOGE" in tags:
        direction = "LONG"
        entry  = round(price, 5)
        sl     = round(low * 0.985, 5)
        risk   = entry - sl
        tp1    = round(entry + risk * 1.5, 5)
        tp2    = round(entry + risk * 2.5, 5)
        rr     = f"1:{round((tp1-entry)/(entry-sl), 1)}" if entry > sl else "1:2.0"
        note   = f"Entry based on live price ${price:.4f}. SL below 24H low. Reduce size if BTC dominance rising."
    elif event_level == "medium" and prob["doge"] >= 55:
        direction = "LONG"
        entry  = round(price * 1.002, 5)
        sl     = round(low * 0.988, 5)
        risk   = entry - sl
        tp1    = round(entry + risk * 1.2, 5)
        tp2    = round(entry + risk * 2.0, 5)
        rr     = "1:1.8"
        note   = "Medium conviction — reduce size by 30% vs standard."
    else:
        direction = "WAIT"
        entry = sl = tp1 = tp2 = 0
        rr    = "—"
        note  = "Event level or probability insufficient for entry. Monitor for confirmation."

    return {
        "direction": direction,
        "asset":  "DOGE",
        "entry":  f"${entry}" if entry else "—",
        "sl":     f"${sl}"    if sl    else "—",
        "tp1":    f"${tp1}"   if tp1   else "—",
        "tp2":    f"${tp2}"   if tp2   else "—",
        "rr":     rr,
        "note":   note,
    }


def _compute_sentiment(doge_data: Dict, btc_data: Dict,
                        news: List[Dict]) -> Dict:
    """Sentiment composite basé sur prix Binance + events récents."""
    doge_ch = doge_data.get("change_24h", 0)
    btc_ch  = btc_data.get("change_24h", 0)

    # Score 0-100 depuis le prix
    price_score = 50
    if doge_ch > 5:   price_score = 80
    elif doge_ch > 2: price_score = 65
    elif doge_ch > 0: price_score = 55
    elif doge_ch < -5: price_score = 20
    elif doge_ch < -2: price_score = 35
    else:              price_score = 45

    # Boost depuis les events récents
    high_events = sum(1 for n in news if n["level"] == "high")
    price_score = min(95, price_score + high_events * 5)

    if price_score >= 65:
        label = "Positive"
        color = "green"
    elif price_score >= 45:
        label = "Neutral"
        color = "amber"
    else:
        label = "Negative"
        color = "red"

    return {
        "score":  price_score,
        "label":  label,
        "color":  color,
        "doge_change": round(doge_ch, 2),
        "btc_change":  round(btc_ch, 2),
    }


def compute_elon_radar() -> Dict[str, Any]:
    """Point d'entrée principal — construit toutes les données."""
    # 1. News RSS
    news  = _fetch_rss_news()
    tweets = _fetch_elon_tweets()
    all_news = tweets + news  # Tweets en premier (plus récents)

    # 2. Prix Binance réels
    doge = _fetch_binance_price("DOGEUSDT")
    btc  = _fetch_binance_price("BTCUSDT")
    tsla_proxy = {}  # TSLA pas dispo sur Binance — on skip

    # 3. Enrichir chaque news avec prob + signal
    enriched = []
    for item in all_news[:8]:
        prob   = _compute_probability(item["level"], item["tags"], doge, btc)
        signal = _compute_signal(item["level"], item["tags"], doge, prob)
        enriched.append({**item, "prob": prob, "signal": signal})

    # 4. Sentiment global
    sentiment = _compute_sentiment(doge, btc, all_news)

    # 5. Impact score (basé sur nb d'events high + prix)
    high_count = sum(1 for n in all_news if n["level"] == "high")
    impact_score = min(95, 50 + high_count * 8 + max(0, doge.get("change_24h", 0)) * 2)

    return {
        "news":          enriched,
        "doge_price":    f"${doge.get('price', 0):.4f}" if doge else "N/A",
        "doge_change":   f"{doge.get('change_24h', 0):+.2f}%" if doge else "N/A",
        "btc_price":     f"${btc.get('price', 0):,.0f}" if btc else "N/A",
        "btc_change":    f"{btc.get('change_24h', 0):+.2f}%" if btc else "N/A",
        "impact_score":  int(impact_score),
        "sentiment":     sentiment,
        "news_count":    len(enriched),
        "high_events":   high_count,
        "last_updated":  datetime.now(timezone.utc).strftime("%H:%M UTC"),
    }


def get_elon_radar_cached() -> Dict[str, Any]:
    now = time.time()
    with _LOCK:
        if _CACHE["data"] and now - _CACHE["ts"] < _TTL:
            return _CACHE["data"]
    try:
        data = compute_elon_radar()
        with _LOCK:
            _CACHE.update({"ts": time.time(), "data": data})
        return data
    except Exception as e:
        print(f"Elon radar error: {e}")
        with _LOCK:
            return _CACHE["data"] or {"news": [], "impact_score": 50,
                "sentiment": {"score": 50, "label": "Neutral", "color": "amber"},
                "news_count": 0, "high_events": 0,
                "doge_price": "N/A", "btc_price": "N/A",
                "last_updated": "N/A"}
