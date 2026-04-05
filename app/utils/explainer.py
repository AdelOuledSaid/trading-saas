def explain_reason(reason: str) -> str:
    if not reason:
        return "Aucune explication disponible."

    explanations = {
        "RSI oversold": "Le RSI est en zone de survente. Cela signifie que le prix a beaucoup baissé et peut rebondir.",
        "RSI overbought": "Le RSI est en zone de surachat. Le prix pourrait corriger.",
        "trend bullish": "Le marché est en tendance haussière, les acheteurs dominent.",
        "trend bearish": "Le marché est en tendance baissière, les vendeurs dominent.",
        "breakout confirmé": "Le prix casse une résistance importante, ce qui peut accélérer le mouvement.",
        "volume actif": "Un volume élevé confirme la validité du mouvement.",
        "tendance forte (ADX élevé)": "Une tendance forte est en cours, souvent exploitable.",
        "volatilité exploitable": "Le marché bouge suffisamment pour générer des opportunités.",
    }

    parts = [p.strip() for p in reason.split("+")]

    result = []
    for p in parts:
        if p in explanations:
            result.append(explanations[p])

    return " ".join(result) if result else reason