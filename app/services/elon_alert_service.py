"""
Elon Alert Service — Surveillance ciblée + scoring strict
Fréquence : toutes les 15 minutes (pas 2min)
Filtre : score minimum 3/5 pour envoyer
Cooldown : 1 heure entre 2 alertes sur le même sujet
"""

import os
import time
import threading
import hashlib
import requests
import feedparser
import re
from datetime import datetime, timezone
from typing import Set, Dict, Optional

TELEGRAM_BOT_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_VIP_CHAT_ID = os.environ.get("TELEGRAM_VIP_CHAT_ID", "")

# ── Fréquence ────────────────────────────────────────────────────
CHECK_INTERVAL_SECONDS = 900   # 15 minutes (pas 2min)
NEWS_CHECK_EVERY       = 2     # news : toutes les 30min (2 cycles)

# ── SCORE SYSTEM ─────────────────────────────────────────────────
# Un article doit scorer >= MINIMUM_SCORE pour déclencher une alerte
MINIMUM_SCORE = 3  # sur 5

# Chaque keyword vaut des points
KEYWORD_SCORES = {
    # Score 3 — événements critiques (toujours alerter)
    "buys bitcoin":     3,
    "sells bitcoin":    3,
    "bought bitcoin":   3,
    "sold bitcoin":     3,
    "doge payment":     3,
    "dogecoin payment": 3,
    "starlink ipo":     3,
    "spacex ipo":       3,
    "elon arrested":    3,
    "tesla bankrupt":   3,

    # Score 2 — événements importants
    "starship launch":  2,
    "starship flight":  2,
    "starship test":    2,
    "mentions doge":    2,
    "mentions dogecoin":2,
    "tweets doge":      2,
    "tweets dogecoin":  2,
    "elon musk doge":   2,
    "nasa contract":    2,
    "nasa award":       2,
    "tesla earnings":   2,
    "tesla delivery":   2,
    "bitcoin treasury": 2,
    "crypto ban":       2,
    "sec crypto":       2,

    # Score 1 — contexte (jamais suffit seul)
    "elon musk":        1,
    "spacex":           1,
    "starship":         1,
    "dogecoin":         1,
    "doge":             1,
    "tesla":            1,
    "bitcoin":          1,
    "btc":              1,
}

# Mots qui RÉDUISENT le score (bruit)
NEGATIVE_KEYWORDS = [
    "opinion", "analysis", "how to", "tutorial", "review",
    "history of", "what is", "explained", "guide", "vs ",
    "price prediction", "will doge", "could doge", "might",
    "rumor", "rumour", "specul", "reportedly", "allegedly",
    "fan", "community", "meme", "joke", "parody",
    "yesterday", "last week", "last month", "last year",
    "2023", "2022", "2021", "2020", "2019",
]

# ── Nitter instances ──────────────────────────────────────────────
NITTER_INSTANCES = [
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
    "https://nitter.1d4.us",
]

# RSS ciblés — seulement les plus fiables
NEWS_RSS = [
    "https://news.google.com/rss/search?q=Elon+Musk+Dogecoin+DOGE+crypto&hl=en&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=SpaceX+Starship+launch+2026&hl=en&gl=US&ceid=US:en",
    "https://cointelegraph.com/rss/tag/elon-musk",
]

# ── État ─────────────────────────────────────────────────────────
import json

# Fichier de persistance : evite de rejouer d'anciennes alertes apres un redemarrage
_SENT_FILE = os.environ.get("ELON_SENT_FILE", "/tmp/elon_sent_hashes.json")


def _load_sent() -> Set[str]:
    try:
        with open(_SENT_FILE) as f:
            return set(json.load(f))
    except Exception:
        return set()


def _save_sent() -> None:
    try:
        with open(_SENT_FILE, "w") as f:
            json.dump(list(_sent_hashes), f)
    except Exception as e:
        print(f"[ElonAlert] ⚠️  save sent failed: {e}")


_sent_hashes: Set[str] = _load_sent()
_topic_cooldown: Dict[str, float] = {}   # topic → timestamp dernier envoi
_COOLDOWN_SECONDS = 3600  # 1h entre 2 alertes du même topic
_running = False
_thread: Optional[threading.Thread] = None


def _hash(text: str) -> str:
    return hashlib.md5(text[:100].encode()).hexdigest()


def _compute_score(title: str, summary: str = "") -> int:
    """Calcule le score de pertinence 0-5."""
    text = (title + " " + summary).lower()

    # Pénalité si article vieux / bruit
    for neg in NEGATIVE_KEYWORDS:
        if neg in text:
            return 0  # ignorer directement

    # Calculer le score
    score = 0
    for keyword, points in KEYWORD_SCORES.items():
        if keyword in text:
            score += points
            if score >= 5:
                return 5  # cap à 5

    return min(score, 5)


def _get_topic(title: str) -> str:
    """Identifie le topic pour le cooldown."""
    t = title.lower()
    if "doge" in t or "dogecoin" in t:  return "doge"
    if "starship" in t:                  return "starship"
    if "bitcoin" in t or "btc" in t:    return "bitcoin"
    if "tesla" in t:                     return "tesla"
    if "nasa" in t:                      return "nasa"
    return "general"


def _is_in_cooldown(topic: str) -> bool:
    """Vérifie si on a déjà envoyé une alerte sur ce topic récemment."""
    last = _topic_cooldown.get(topic, 0)
    return (time.time() - last) < _COOLDOWN_SECONDS


def _set_cooldown(topic: str) -> None:
    _topic_cooldown[topic] = time.time()


def _get_emoji(title: str) -> str:
    t = title.lower()
    if "starship" in t or "launch" in t: return "🚀"
    if "doge" in t or "dogecoin" in t:   return "🐕"
    if "bitcoin" in t or "btc" in t:     return "₿"
    if "nasa" in t:                       return "🛸"
    if "tesla" in t:                      return "⚡"
    return "📡"


def _get_impact_text(title: str) -> str:
    """
    Lecture qualitative de la direction possible — PAS une prevision chiffree.
    Aucun pourcentage n'est invente. On indique seulement les actifs a
    surveiller et un biais directionnel, a confirmer sur le graphique.
    """
    t = title.lower()

    # Evenement baissier explicite
    if "sells bitcoin" in t or "sold bitcoin" in t:
        return (
            "📉 Biais : prudence / *risk-off* possible\n"
            "👀 A surveiller : *BTC*\n"
            "🔎 Reaction a confirmer sur le graphique"
        )

    # Evenement haussier fort (achat / tresorerie / paiement)
    if (
        "buys bitcoin" in t or "bought bitcoin" in t
        or "bitcoin treasury" in t
        or "doge payment" in t or "dogecoin payment" in t
    ):
        return (
            "📈 Biais : *risk-on* possible\n"
            "👀 A surveiller : *BTC*, *DOGE*\n"
            "🔎 Direction a confirmer avant toute decision"
        )

    # Mentions DOGE / Dogecoin
    if "doge" in t or "dogecoin" in t:
        return (
            "🐕 Biais : *DOGE* sensible aux propos d'Elon Musk\n"
            "👀 A surveiller : *DOGE*, et *BTC* par correlation\n"
            "🔎 Ampleur incertaine — a confirmer sur le graphique"
        )

    # Lancement / Starship
    if "starship" in t or "launch" in t:
        return (
            "🚀 Biais : sentiment crypto potentiellement positif\n"
            "👀 A surveiller : *DOGE*, *BTC*\n"
            "🔎 Effet souvent court et incertain"
        )

    # NASA / contrats
    if "nasa" in t:
        return (
            "⚡ Biais : possible soutien sur *TSLA*\n"
            "👀 A surveiller : *TSLA*, *BTC* (correlation faible)"
        )

    return (
        "📊 A surveiller : *DOGE* / *BTC*\n"
        "🔎 Direction a confirmer sur le graphique"
    )


def _format_message(title: str, source: str, link: str, score: int) -> str:
    emoji   = _get_emoji(title)
    impact  = _get_impact_text(title)
    now     = datetime.now(timezone.utc).strftime("%H:%M UTC")
    urgency = "🔴 HIGH" if score >= 4 else "🟡 MEDIUM"

    return f"""⚡ *ELON ALERT* — {now}
{urgency} (score {score}/5)

{emoji} *{title[:180]}*
📰 {source}

━━━━━━━━━━━━━━━━━━
🧭 *Lecture rapide* (a confirmer)
{impact}

🔗 [Read more]({link})
━━━━━━━━━━━━━━━━━━
⚠️ _Information, pas un conseil en investissement. Verifiez vous-meme avant toute decision._
🔒 _VIP — VelWolef Elon Radar_"""


def send_telegram(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_VIP_CHAT_ID:
        print("[ElonAlert] ⚠️  Bot token or chat ID missing")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id":    TELEGRAM_VIP_CHAT_ID,
                "text":       message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": False,
            },
            timeout=10
        )
        ok = r.status_code == 200
        if ok:
            print(f"[ElonAlert] ✅ Sent: {message[:60]}...")
        else:
            print(f"[ElonAlert] ❌ {r.status_code}: {r.text[:100]}")
        return ok
    except Exception as e:
        print(f"[ElonAlert] ❌ {e}")
        return False


def _process_item(title: str, source: str, link: str, summary: str = "") -> None:
    """Pipeline complet : score → cooldown → envoi."""
    # Dedup sur le lien (plus fiable que le titre, qui varie d'un flux a l'autre)
    h = _hash(link or title)
    if h in _sent_hashes:
        return  # déjà envoyé

    score = _compute_score(title, summary)
    if score < MINIMUM_SCORE:
        print(f"[ElonAlert] ⬇️  Filtered (score {score}/5): {title[:60]}")
        return

    topic = _get_topic(title)
    if _is_in_cooldown(topic):
        print(f"[ElonAlert] ⏳ Cooldown ({topic}): {title[:60]}")
        return

    # Tout est OK — envoyer
    msg = _format_message(title, source, link, score)
    if send_telegram(msg):
        _sent_hashes.add(h)
        _set_cooldown(topic)
        _save_sent()  # persister pour survivre aux redemarrages

        # Garder max 1000 hashes
        if len(_sent_hashes) > 1000:
            old = list(_sent_hashes)[:200]
            for o in old:
                _sent_hashes.discard(o)
            _save_sent()


def _check_tweets() -> None:
    for instance in NITTER_INSTANCES:
        try:
            feed = feedparser.parse(f"{instance}/elonmusk/rss", request_headers={"User-Agent": "Mozilla/5.0"})
            if not feed.entries:
                continue
            for entry in feed.entries[:5]:
                title   = entry.get("title", "")
                summary = re.sub(r'<[^>]+>', '', entry.get("summary", ""))[:300]
                link    = entry.get("link", "#").replace(instance, "https://x.com")
                _process_item(title, "X (Elon Musk)", link, summary)
            break
        except Exception as e:
            print(f"[ElonAlert] Nitter {instance}: {e}")
            continue


def _check_news() -> None:
    for url in NEWS_RSS:
        try:
            feed = feedparser.parse(url)
            source = feed.feed.get("title", "News")
            for entry in feed.entries[:5]:
                title   = entry.get("title", "")
                summary = re.sub(r'<[^>]+>', '', entry.get("summary", ""))[:300]
                link    = entry.get("link", "#")
                _process_item(title, source, link, summary)
        except Exception as e:
            print(f"[ElonAlert] RSS: {e}")
            continue


def _monitor_loop() -> None:
    print(f"[ElonAlert] 🚀 Started — checking every {CHECK_INTERVAL_SECONDS//60}min, min score {MINIMUM_SCORE}/5")
    cycle = 0
    while _running:
        try:
            print(f"[ElonAlert] 🔍 Cycle {cycle} — checking tweets...")
            _check_tweets()

            if cycle % NEWS_CHECK_EVERY == 0:
                print(f"[ElonAlert] 📰 Checking news...")
                _check_news()

            cycle += 1
        except Exception as e:
            print(f"[ElonAlert] Loop error: {e}")

        # Attendre CHECK_INTERVAL_SECONDS secondes
        for _ in range(CHECK_INTERVAL_SECONDS):
            if not _running:
                break
            time.sleep(1)

    print("[ElonAlert] 🛑 Stopped")


def start_monitoring() -> None:
    global _running, _thread
    if _running:
        return
    if not TELEGRAM_BOT_TOKEN:
        print("[ElonAlert] ⚠️  TELEGRAM_BOT_TOKEN not set — disabled")
        return
    _running = True
    _thread  = threading.Thread(target=_monitor_loop, daemon=True, name="ElonAlertMonitor")
    _thread.start()


def stop_monitoring() -> None:
    global _running
    _running = False


def send_test_alert() -> bool:
    """Test la configuration Telegram."""
    return send_telegram(
        "🧪 *VelWolef Elon Radar — Test*\n\n"
        "✅ Configuration OK\n\n"
        f"Checking every {CHECK_INTERVAL_SECONDS//60}min\n"
        f"Minimum score: {MINIMUM_SCORE}/5\n"
        f"Cooldown: {_COOLDOWN_SECONDS//60}min per topic\n\n"
        "_VelWolef VIP_"
    )
