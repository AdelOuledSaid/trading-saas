def get_pricing_data(lang):
    if lang == "fr":
        return {
            "price": "29€",
            "currency": "EUR",
            "symbol": "€"
        }

    elif lang == "en":
        return {
            "price": "$29",
            "currency": "USD",
            "symbol": "$"
        }

    elif lang == "es":
        return {
            "price": "29€",
            "currency": "EUR",
            "symbol": "€"
        }

    return {
        "price": "29€",
        "currency": "EUR",
        "symbol": "€"
    }