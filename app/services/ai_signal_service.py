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
        if rsi < 30 or rsi > 70:
            score += 12
        elif 30 <= rsi < 40 or 60 < rsi <= 70:
            score += 6
        elif 45 <= rsi <= 55:
            score -= 4

    # Trend
    if trend in {"bullish", "bearish"}:
        score += 12
    elif trend == "neutral":
        score -= 3

    # Breakout
    if breakout:
        score += 10

    # Volume
    if volume:
        score += 5

    # ADX = force de tendance
    if adx is not None:
        if adx >= 30:
            score += 10
        elif adx >= 22:
            score += 6
        elif adx < 18:
            score -= 5

    # ATR : présence de volatilité exploitable
    if atr is not None:
        if atr > 0:
            score += 3

    # News sentiment optionnel
    if news:
        score += max(-5, min(5, int(news * 10)))

    return max(50, min(score, 95))


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
            reasons.append("RSI en zone d'accumulation")
        elif 60 < rsi <= 70:
            reasons.append("RSI en zone de momentum")

    # Trend
    if trend == "bullish":
        reasons.append("trend bullish")
    elif trend == "bearish":
        reasons.append("trend bearish")
    elif trend == "neutral":
        reasons.append("trend neutral")

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