import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


def get_client():
    api_key = os.getenv("OPENAI_API_KEY", "").strip()

    if not api_key:
        return None

    return OpenAI(api_key=api_key)


def generate_daily_briefing(btc_data: str, gold_data: str, eco_data: str) -> str:
    """
    Génère un briefing trading ULTRA PREMIUM (structure hedge fund)
    """

    client = get_client()

    # ✅ FALLBACK SI PAS DE CLÉ
    fallback = f"""
📊 Morning Brief

BTC:
{btc_data}

Gold:
{gold_data}

Macro:
{eco_data}

Plan du jour :
- attendre confirmation
- surveiller volatilité
- privilégier gestion du risque
""".strip()

    if client is None:
        return fallback

    try:
        prompt = f"""
Tu es un analyste macro & trader professionnel travaillant dans un hedge fund.

Ta mission :
Produire un briefing trading PREMIUM, structuré, clair et directement exploitable.

IMPORTANT :
- Pas de blabla inutile
- Style professionnel
- Phrase courte
- Orientation trading
- Focus opportunités + risque

========================
STRUCTURE OBLIGATOIRE
========================

## 🧠 1. Market Sentiment
- Biais global (Risk-on / Risk-off)
- Direction dominante
- Contexte macro rapide

## ₿ 2. Bitcoin (BTC)
- Tendance actuelle
- Zones clés
- Scénarios

## 🪙 3. Gold (XAUUSD)
- Tendance
- Zones clés

## 🌍 4. Macro & News Impact
- Événements importants
- Impact marché

## 🎯 5. Opportunités du jour
- Actifs à surveiller
- Conditions d'entrée

## ⚠️ 6. Risk Management
- Niveau de risque
- Pièges possibles

## 📌 7. Conclusion Trading
- Biais final
- Stratégie

========================
DONNÉES
========================

BTC:
{btc_data}

GOLD:
{gold_data}

MACRO:
{eco_data}
"""

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt
        )

        text = getattr(response, "output_text", "").strip()

        if not text:
            return fallback

        return text

    except Exception:
        return fallback