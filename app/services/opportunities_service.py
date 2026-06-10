"""
Service de scoring des opportunités — calcule en temps réel depuis Binance.
Score basé sur : momentum 24h, volume relatif, RSI simplifié, proximité support.
"""
import time
import threading
import requests
from typing import List, Dict, Any

# ── Cache module-level ─────────────────────────────────────────
_OPP_CACHE = {"ts": 0, "data": []}
_OPP_LOCK  = threading.Lock()
_OPP_TTL   = 180  # 3 minutes

ASSETS = [
    {"symbol": "SOLUSDT",  "name": "Solana",    "ticker": "SOL",  "tv": "BINANCE:SOLUSDT"},
    {"symbol": "LINKUSDT", "name": "Chainlink", "ticker": "LINK", "tv": "BINANCE:LINKUSDT"},
    {"symbol": "AVAXUSDT", "name": "Avalanche", "ticker": "AVAX", "tv": "BINANCE:AVAXUSDT"},
    {"symbol": "NEARUSDT", "name": "NEAR",      "ticker": "NEAR", "tv": "BINANCE:NEARUSDT"},
    {"symbol": "SUIUSDT",  "name": "Sui",       "ticker": "SUI",  "tv": "BINANCE:SUIUSDT"},
    {"symbol": "APTUSDT",  "name": "Aptos",     "ticker": "APT",  "tv": "BINANCE:APTUSDT"},
]

def _get_binance_data(symbols: List[str]) -> Dict[str, dict]:
    """Fetch 24h ticker stats depuis Binance."""
    try:
        syms = str([s for s in symbols]).replace("'", '"').replace(" ", "")
        r = requests.get(
            "https://api.binance.com/api/v3/ticker/24hr",
            params={"symbols": syms},
            timeout=8
        )
        r.raise_for_status()
        return {item["symbol"]: item for item in r.json()}
    except Exception:
        return {}


def _score_asset(ticker_data: dict) -> int:
    """
    Score 0-100 basé sur :
    - Momentum 24h (change%) : 40 pts
    - Volume relatif         : 30 pts
    - Stabilité (pas trop volatile) : 20 pts
    - Proximity high (près du high 24h) : 10 pts
    """
    try:
        change  = float(ticker_data.get("priceChangePercent", 0))
        price   = float(ticker_data.get("lastPrice", 0))
        high    = float(ticker_data.get("highPrice", price))
        low     = float(ticker_data.get("lowPrice", price))
        volume  = float(ticker_data.get("quoteVolume", 0))
        count   = int(ticker_data.get("count", 0))

        # Momentum score (0-40)
        if change >= 5:       m_score = 40
        elif change >= 2:     m_score = 30
        elif change >= 0:     m_score = 20
        elif change >= -2:    m_score = 10
        else:                 m_score = 0

        # Volume score (0-30) — basé sur le volume brut
        if volume >= 500_000_000:    v_score = 30
        elif volume >= 200_000_000:  v_score = 25
        elif volume >= 100_000_000:  v_score = 20
        elif volume >= 50_000_000:   v_score = 15
        elif volume >= 20_000_000:   v_score = 10
        else:                        v_score = 5

        # Stabilité — faible range = compression (bon) (0-20)
        rng = (high - low) / low * 100 if low > 0 else 0
        if rng < 3:      s_score = 20
        elif rng < 6:    s_score = 15
        elif rng < 10:   s_score = 10
        else:            s_score = 5

        # Proximity high (0-10)
        if high > 0 and price > 0:
            prox = (price - low) / (high - low) if high != low else 0
            h_score = int(prox * 10)
        else:
            h_score = 5

        return min(100, m_score + v_score + s_score + h_score)

    except Exception:
        return 50


def _state_from_score(score: int, change: float) -> tuple:
    """Retourne (state_label, state_class)."""
    if score >= 85:
        return "TRIGGERING", "triggering"
    elif score >= 70:
        return "ARMING", "arming"
    elif score >= 55:
        return "PRESSURE", "pressure"
    elif score >= 40:
        return "WATCH", "watch"
    else:
        return "STANDBY", "standby"


def _tier_from_score(score: int) -> str:
    if score >= 90: return "A+"
    if score >= 80: return "A"
    if score >= 70: return "B+"
    if score >= 60: return "B"
    return "C"


def _bias_from_change(change: float) -> str:
    if change >= 3:   return "Expansion"
    if change >= 1:   return "Breakout"
    if change >= 0:   return "Rebound"
    if change >= -2:  return "Pending"
    return "Compression"


def _window_from_state(state: str) -> str:
    return {"TRIGGERING": "Open", "ARMING": "Watching",
            "PRESSURE": "Monitor", "WATCH": "Standby",
            "STANDBY": "Standby"}.get(state, "Standby")


def _description(name: str, state: str, change: float, score: int) -> str:
    if state == "TRIGGERING":
        return f"{name} shows dominant structure with clear leadership and elevated conviction."
    if state == "ARMING":
        return f"Net compression and subsurface energy building in {name}. Monitor closely."
    if state == "PRESSURE":
        return f"Interesting recovery in {name} but validation still needed on the hierarchy."
    if state == "WATCH":
        return f"Active standby. {name} capable of moving up the hierarchy on confirmation."
    return f"{name} is in compression mode. No actionable setup yet."


def compute_opportunities() -> List[Dict[str, Any]]:
    """Calcule les scores en temps réel depuis Binance."""
    symbols = [a["symbol"] for a in ASSETS]
    ticker_data = _get_binance_data(symbols)

    results = []
    for asset in ASSETS:
        td = ticker_data.get(asset["symbol"], {})
        score  = _score_asset(td)
        change = float(td.get("priceChangePercent", 0))
        price  = float(td.get("lastPrice", 0))
        state, state_class = _state_from_score(score, change)
        tier   = _tier_from_score(score)
        bias   = _bias_from_change(change)
        window = _window_from_state(state)

        results.append({
            **asset,
            "score":       score,
            "change":      change,
            "price":       price,
            "state":       state,
            "state_class": state_class,
            "tier":        tier,
            "bias":        bias,
            "window":      window,
            "description": _description(asset["name"], state, change, score),
            "heat":        "Elevated" if score >= 70 else "Moderate" if score >= 50 else "Low",
        })

    return sorted(results, key=lambda x: x["score"], reverse=True)


def get_opportunities_cached() -> List[Dict[str, Any]]:
    """Retourne les opportunités avec cache 3 minutes."""
    now = time.time()

    with _OPP_LOCK:
        if _OPP_CACHE["data"] and now - _OPP_CACHE["ts"] < _OPP_TTL:
            return _OPP_CACHE["data"]

    # Refresh
    try:
        data = compute_opportunities()
        with _OPP_LOCK:
            _OPP_CACHE.update({"ts": time.time(), "data": data})
        return data
    except Exception:
        with _OPP_LOCK:
            return _OPP_CACHE["data"] or []
