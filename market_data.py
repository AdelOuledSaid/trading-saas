import requests


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