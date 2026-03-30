from dotenv import load_dotenv
load_dotenv()

from ai_briefing import generate_daily_briefing


# Données TEST
btc_data = """
Prix actuel : 84250 USD
Variation 24h : +1.8%
Tendance court terme : haussière
Support : 83500
Résistance : 85000
"""

gold_data = """
Prix actuel : 3085 USD
Variation 24h : -0.4%
Tendance court terme : neutre à baissière
Support : 3068
Résistance : 3100
"""

eco_data = """
- 14:30 : Inflation CPI USA
- 16:00 : Indice de confiance des consommateurs
- 20:00 : Discours d'un membre de la Fed
"""


# Génération du briefing
result = generate_daily_briefing(btc_data, gold_data, eco_data)

# Affichage
print("\n===== BRIEFING IA =====\n")
print(result)