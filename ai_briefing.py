import os
from openai import OpenAI
from dotenv import load_dotenv

# Charger les variables d'environnement (.env)
load_dotenv()

# Initialisation du client OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def generate_daily_briefing(btc_data: str, gold_data: str, eco_data: str) -> str:
    """
    Génère un briefing trading complet (BTC + OR + macro)
    """

    try:
        prompt = f"""
Tu es un analyste financier professionnel spécialisé en trading.

Ta mission :
Générer un briefing de marché clair, structuré et exploitable pour un trader.

Structure OBLIGATOIRE :

## 1. Résumé exécutif
- Vue globale du marché
- Sentiment (risk-on / risk-off)

## 2. Analyse du Bitcoin
- Tendance
- Niveaux clés
- Scénarios possibles

## 3. Analyse de l'Or
- Tendance
- Niveaux clés
- Scénarios possibles

## 4. Événements économiques
- Impact attendu
- Importance des événements

## 5. Risques à surveiller
- Volatilité
- Cassures de niveaux
- Faux signaux

## 6. Conclusion opérationnelle
- Lecture trading claire
- Biais (achat / vente / prudence)

Données :

Bitcoin :
{btc_data}

Or :
{gold_data}

Macro :
{eco_data}

Contraintes :
- Style professionnel
- Pas de phrases inutiles
- Analyse concrète
- Adapté au trading court terme
"""

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt
        )

        return response.output[0].content[0].text

    except Exception as e:
        return f"❌ Erreur génération briefing : {str(e)}"