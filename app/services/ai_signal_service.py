import random


# =========================
# SAFE HELPERS
# =========================
def _safe_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_bool(value):
    if isinstance(value, bool):
        return value

    if value is None:
        return False

    if isinstance(value, (int, float)):
        return bool(value)

    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "on"}

    return False


# =========================
# CONFIDENCE SCORE
# =========================
def compute_confidence(data):
    score = 50

    rsi = _safe_float(data.get("rsi"))
    trend = str(data.get("trend", "")).strip().lower()
    breakout = _safe_bool(data.get("breakout"))
    volume = _safe_bool(data.get("volume"))
    adx = _safe_float(data.get("adx"))
    atr = _safe_float(data.get("atr"))
    news = _safe_float(data.get("news_sentiment"), 0)

    # RSI
    if rsi is not None:
        if rsi < 30:
            score += 20
        elif rsi > 70:
            score += 20
        elif 30 <= rsi < 40:
            score += 10
        elif 60 < rsi <= 70:
            score += 10
        elif 45 <= rsi <= 55:
            score -= 5

    # Trend
    if trend == "bullish":
        score += 15
    elif trend == "bearish":
        score += 15
    elif trend == "neutral":
        score -= 3

    # Breakout
    if breakout:
        score += 15

    # Volume
    if volume:
        score += 5

    # ADX
    if adx is not None:
        if adx >= 30:
            score += 12
        elif adx >= 22:
            score += 8
        elif adx < 18:
            score -= 5

    # ATR (volatilité)
    if atr is not None and atr > 0:
        score += 4

    # News sentiment
    if news:
        score += max(-5, min(5, int(news * 10)))

    # Petit random réaliste
    score += random.randint(-2, 2)

    return max(50, min(score, 95))


# =========================
# GENERATE REASON
# =========================
def generate_reason(data):
    reasons = []

    rsi = _safe_float(data.get("rsi"))
    trend = str(data.get("trend", "")).strip().lower()
    breakout = _safe_bool(data.get("breakout"))
    volume = _safe_bool(data.get("volume"))
    adx = _safe_float(data.get("adx"))
    atr = _safe_float(data.get("atr"))

    # RSI
    if rsi is not None:
        if rsi < 30:
            reasons.append("RSI oversold")
        elif rsi > 70:
            reasons.append("RSI overbought")
        elif 30 <= rsi < 40:
            reasons.append("RSI accumulation")
        elif 60 < rsi <= 70:
            reasons.append("RSI momentum")

    # Trend
    if trend == "bullish":
        reasons.append("trend bullish")
    elif trend == "bearish":
        reasons.append("trend bearish")

    # Breakout
    if breakout:
        reasons.append("breakout confirmé")

    # Volume
    if volume:
        reasons.append("volume actif")

    # ADX
    if adx is not None:
        if adx >= 30:
            reasons.append("tendance forte (ADX élevé)")
        elif adx >= 22:
            reasons.append("tendance validée par ADX")

    # ATR
    if atr is not None and atr > 0:
        reasons.append("volatilité exploitable")

    return " + ".join(reasons) if reasons else "Analyse technique neutre"