import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def generate_daily_briefing(btc_data: str, gold_data: str, eco_data: str) -> str:
    """
    Génère un briefing trading ULTRA PREMIUM (structure hedge fund)
    """

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
- Zones clés (support / résistance)
- Scénario haussier
- Scénario baissier
- Niveau critique

## 🪙 3. Gold (XAUUSD)
- Tendance
- Rôle (refuge ou pression)
- Zones clés
- Scénarios

## 🌍 4. Macro & News Impact
- Événements économiques importants
- Impact potentiel sur le marché
- Niveau de volatilité attendu

## 🎯 5. Opportunités du jour
- Actifs à surveiller
- Conditions d'entrée idéales
- Type de setup (breakout / pullback / range)

## ⚠️ 6. Risk Management
- Niveau de risque global (faible / modéré / élevé)
- Pièges possibles (fake breakout, news, etc.)

## 📌 7. Conclusion Trading
- Biais final : BUY / SELL / NEUTRAL
- Stratégie recommandée (attente / agressif / conservateur)

========================
DONNÉES
========================

BTC:
{btc_data}

GOLD:
{gold_data}

MACRO:
{eco_data}

========================
CONTRAINTES
========================

- Maximum 500 mots
- Lisible rapidement
- Style pro
- Pas de répétition
- Pas de disclaimer inutile
"""

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt
        )

        return response.output[0].content[0].text

    except Exception as e:
        return f"❌ Erreur génération briefing : {str(e)}"