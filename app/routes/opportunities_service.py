"""
Service de scoring des opportunités — calcule en temps réel depuis Binance.
Score basé sur : momentum 24h, volume relatif, RSI simplifié, proximité support.
Enrichi avec : rotation capital, liquidité/stop hunts, signal d'exécution, timer fenêtre.
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
    {"symbol": "ETHUSDT",  "name": "Ethereum",  "ticker": "ETH",  "tv": "BINANCE:ETHUSDT"},
    {"symbol": "BTCUSDT",  "name": "Bitcoin",   "ticker": "BTC",  "tv": "BINANCE:BTCUSDT"},
]

def _get_binance_data(symbols: List[str]) -> Dict[str, dict]:
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
    try:
        change  = float(ticker_data.get("priceChangePercent", 0))
        price   = float(ticker_data.get("lastPrice", 0))
        high    = float(ticker_data.get("highPrice", price))
        low     = float(ticker_data.get("lowPrice", price))
        volume  = float(ticker_data.get("quoteVolume", 0))

        # Momentum (0-40)
        if change >= 5:       m_score = 40
        elif change >= 2:     m_score = 30
        elif change >= 0:     m_score = 20
        elif change >= -2:    m_score = 10
        else:                 m_score = 0

        # Volume (0-30)
        if volume >= 500_000_000:    v_score = 30
        elif volume >= 200_000_000:  v_score = 25
        elif volume >= 100_000_000:  v_score = 20
        elif volume >= 50_000_000:   v_score = 15
        elif volume >= 20_000_000:   v_score = 10
        else:                        v_score = 5

        # Stabilité (0-20)
        rng = (high - low) / low * 100 if low > 0 else 0
        if rng < 3:      s_score = 20
        elif rng < 6:    s_score = 15
        elif rng < 10:   s_score = 10
        else:            s_score = 5

        # Proximity high (0-10)
        h_score = 0
        if high > 0 and price > 0 and high != low:
            prox = (price - low) / (high - low)
            h_score = int(prox * 10)

        return min(100, m_score + v_score + s_score + h_score)
    except Exception:
        return 0

def _state_from_score(score: int, change: float):
    if score >= 75 and change > 0:
        return "TRIGGERING", "state-trigger"
    if score >= 60:
        return "ARMING", "state-arming"
    if score >= 45:
        return "PRESSURE", "state-pressure"
    if score >= 30:
        return "WATCH", "state-watch"
    return "STANDBY", "state-standby"

def _tier_from_score(score: int) -> str:
    if score >= 80: return "A+"
    if score >= 70: return "A"
    if score >= 60: return "B+"
    if score >= 50: return "B"
    return "C"

def _bias_from_change(change: float) -> str:
    if change >= 3:   return "Expansion"
    if change >= 1:   return "Breakout"
    if change >= 0:   return "Rebound"
    if change >= -2:  return "Pending"
    return "Compression"

def _window_from_state(state: str) -> str:
    return {
        "TRIGGERING": "Open",
        "ARMING": "Watching",
        "PRESSURE": "Monitor",
        "WATCH": "Standby",
        "STANDBY": "Standby"
    }.get(state, "Standby")

def _window_minutes(state: str) -> int:
    """Fenêtre d'exécution estimée en minutes."""
    return {
        "TRIGGERING": 45,
        "ARMING": 120,
        "PRESSURE": 240,
        "WATCH": 480,
        "STANDBY": 0
    }.get(state, 0)

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

def _compute_rotation_signal(all_data: Dict[str, dict]) -> Dict[str, Any]:
    """
    Détecte la rotation du capital : compare BTC dominance proxy
    (BTC volume vs altcoin volumes) pour identifier où l'argent va.
    """
    btc_vol  = float(all_data.get("BTCUSDT", {}).get("quoteVolume", 0))
    eth_vol  = float(all_data.get("ETHUSDT", {}).get("quoteVolume", 0))
    alts_vol = sum(
        float(all_data.get(s, {}).get("quoteVolume", 0))
        for s in ["SOLUSDT","LINKUSDT","AVAXUSDT","NEARUSDT","SUIUSDT","APTUSDT"]
    )
    total = btc_vol + eth_vol + alts_vol

    if total == 0:
        return {"phase": "Unknown", "direction": "—", "intensity": 0, "detail": "Insufficient data"}

    btc_share  = btc_vol / total * 100
    eth_share  = eth_vol / total * 100
    alts_share = alts_vol / total * 100

    if btc_share > 50:
        phase = "BTC Dominance"
        direction = "Capital concentrated in BTC"
        intensity = int(btc_share)
    elif eth_share > 25:
        phase = "ETH Rotation"
        direction = "Capital moving toward ETH"
        intensity = int(eth_share)
    elif alts_share > 35:
        phase = "Alt Season"
        direction = "Capital rotating into altcoins"
        intensity = int(alts_share)
    else:
        phase = "Mixed"
        direction = "No clear rotation signal"
        intensity = 0

    return {
        "phase": phase,
        "direction": direction,
        "intensity": intensity,
        "btc_share": round(btc_share, 1),
        "eth_share": round(eth_share, 1),
        "alts_share": round(alts_share, 1),
    }

def _compute_liquidity_zones(ticker_data: dict, price: float) -> Dict[str, Any]:
    """
    Calcule les zones de liquidité probables (stop hunt targets).
    Basé sur high/low 24h et la position actuelle du prix.
    """
    try:
        high = float(ticker_data.get("highPrice", price))
        low  = float(ticker_data.get("lowPrice", price))
        rng  = high - low

        # Zones de liquidité = autour des extrêmes 24h
        buy_side  = round(high + rng * 0.02, 4)   # 2% au-dessus du high
        sell_side = round(low  - rng * 0.02, 4)   # 2% sous le low

        # Distance du prix actuel aux zones
        dist_to_buy  = round((buy_side - price) / price * 100, 2) if price > 0 else 0
        dist_to_sell = round((price - sell_side) / price * 100, 2) if price > 0 else 0

        # Quelle zone est plus proche = probable prochaine cible
        if abs(dist_to_buy) < abs(dist_to_sell):
            nearest = "buy-side"
            nearest_dist = dist_to_buy
            nearest_level = buy_side
        else:
            nearest = "sell-side"
            nearest_dist = dist_to_sell
            nearest_level = sell_side

        return {
            "buy_side":     buy_side,
            "sell_side":    sell_side,
            "dist_to_buy":  dist_to_buy,
            "dist_to_sell": dist_to_sell,
            "nearest":      nearest,
            "nearest_dist": abs(nearest_dist),
            "nearest_level": nearest_level,
            "range_pct":    round(rng / low * 100, 2) if low > 0 else 0,
        }
    except Exception:
        return {"buy_side": 0, "sell_side": 0, "nearest": "—", "nearest_dist": 0, "nearest_level": 0, "range_pct": 0}

def _compute_execution_signal(ticker_data: dict, score: int, state: str, change: float, price: float) -> Dict[str, Any]:
    """
    Génère un signal d'exécution suggéré basé sur le scoring.
    SL = 2% sous le low 24h, TP = 2x le risque.
    """
    try:
        high = float(ticker_data.get("highPrice", price))
        low  = float(ticker_data.get("lowPrice", price))

        if state in ["TRIGGERING", "ARMING"] and change >= 0:
            direction = "LONG"
            entry  = round(price, 4)
            sl     = round(low * 0.985, 4)   # 1.5% sous le low
            risk   = entry - sl
            tp1    = round(entry + risk * 1.5, 4)
            tp2    = round(entry + risk * 2.5, 4)
            rr     = round(risk / entry * 100, 2) if entry > 0 else 0
        elif state == "PRESSURE" and change < -2:
            direction = "SHORT"
            entry  = round(price, 4)
            sl     = round(high * 1.015, 4)
            risk   = sl - entry
            tp1    = round(entry - risk * 1.5, 4)
            tp2    = round(entry - risk * 2.5, 4)
            rr     = round(risk / entry * 100, 2) if entry > 0 else 0
        else:
            direction = "WAIT"
            entry = sl = tp1 = tp2 = rr = 0

        return {
            "direction": direction,
            "entry":     entry,
            "sl":        sl,
            "tp1":       tp1,
            "tp2":       tp2,
            "rr":        rr,
            "confidence": score,
        }
    except Exception:
        return {"direction": "WAIT", "entry": 0, "sl": 0, "tp1": 0, "tp2": 0, "rr": 0, "confidence": 0}

def _format_price(p: float) -> str:
    if p == 0: return "—"
    if p >= 1000: return f"${p:,.0f}"
    if p >= 1:    return f"${p:.2f}"
    return f"${p:.4f}"

def compute_opportunities() -> List[Dict[str, Any]]:
    symbols = [a["symbol"] for a in ASSETS]
    ticker_data = _get_binance_data(symbols)

    rotation = _compute_rotation_signal(ticker_data)

    results = []
    for asset in ASSETS:
        td     = ticker_data.get(asset["symbol"], {})
        score  = _score_asset(td)
        change = float(td.get("priceChangePercent", 0))
        price  = float(td.get("lastPrice", 0))
        volume = float(td.get("quoteVolume", 0))
        state, state_class = _state_from_score(score, change)
        tier   = _tier_from_score(score)
        bias   = _bias_from_change(change)
        window = _window_from_state(state)
        liq    = _compute_liquidity_zones(td, price)
        signal = _compute_execution_signal(td, score, state, change, price)

        results.append({
            **asset,
            "score":       score,
            "change":      round(change, 2),
            "price":       price,
            "price_fmt":   _format_price(price),
            "volume":      volume,
            "volume_fmt":  f"${volume/1e6:.0f}M" if volume >= 1e6 else f"${volume:.0f}",
            "state":       state,
            "state_class": state_class,
            "tier":        tier,
            "bias":        bias,
            "window":      window,
            "window_min":  _window_minutes(state),
            "description": _description(asset["name"], state, change, score),
            "heat":        "Elevated" if score >= 70 else "Moderate" if score >= 50 else "Low",
            "liquidity":   liq,
            "signal":      signal,
            "rotation":    rotation,
        })

    return sorted(results, key=lambda x: x["score"], reverse=True)

def get_opportunities_cached() -> List[Dict[str, Any]]:
    now = time.time()
    with _OPP_LOCK:
        if _OPP_CACHE["data"] and now - _OPP_CACHE["ts"] < _OPP_TTL:
            return _OPP_CACHE["data"]
    try:
        data = compute_opportunities()
        with _OPP_LOCK:
            _OPP_CACHE.update({"ts": time.time(), "data": data})
        return data
    except Exception:
        with _OPP_LOCK:
            return _OPP_CACHE["data"] or []
