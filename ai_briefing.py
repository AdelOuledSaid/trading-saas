import os
from dotenv import load_dotenv
from openai import OpenAI

# Charger les variables d'environnement (.env)
load_dotenv()

# Initialisation client OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def generate_daily_briefing(btc_data: str, gold_data: str, eco_data: str) -> str:
    prompt = f"""
Tu es un analyste macro-financier professionnel.

Ta mission :
Rédiger un briefing quotidien en français, clair, structuré et professionnel.

Règles importantes :
- N'invente aucun chiffre
- Utilise uniquement les données fournies
- Sois concret, utile et lisible
- Fais une analyse orientée trading court terme
- Ajoute une conclusion opérationnelle

Données BTC :
{btc_data}

Données OR :
{gold_data}

Événements économiques :
{eco_data}

Structure obligatoire :
1. Résumé exécutif
2. Analyse du Bitcoin
3. Analyse de l'Or
4. Événements économiques du jour
5. Risques à surveiller
6. Conclusion opérationnelle
"""

    response = client.responses.create(
        model="gpt-5.4",
        input=prompt
    )

    return response.output_text.strip()