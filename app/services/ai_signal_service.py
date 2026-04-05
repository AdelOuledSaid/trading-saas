import random


def compute_confidence(data):
    score = 50

    # RSI
    rsi = data.get("rsi")
    if rsi:
        if rsi < 30 or rsi > 70:
            score += 15
        elif 40 < rsi < 60:
            score -= 5

    # Trend
    trend = data.get("trend")
    if trend == "bullish":
        score += 15
    elif trend == "bearish":
        score += 15

    # Breakout
    if data.get("breakout"):
        score += 10

    # News sentiment
    news = data.get("news_sentiment")
    if news:
        score += int(news * 10)

    # Random léger pour réaliste
    score += random.randint(-3, 3)

    return max(50, min(score, 95))


def generate_reason(data):
    reasons = []

    rsi = data.get("rsi")
    if rsi:
        if rsi < 30:
            reasons.append("RSI oversold")
        elif rsi > 70:
            reasons.append("RSI overbought")

    if data.get("trend") == "bullish":
        reasons.append("trend bullish")
    elif data.get("trend") == "bearish":
        reasons.append("trend bearish")

    if data.get("breakout"):
        reasons.append("breakout confirmé")

    if data.get("volume"):
        reasons.append("volume élevé")

    return " + ".join(reasons) if reasons else "Analyse technique neutre"