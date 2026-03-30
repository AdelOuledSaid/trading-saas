from datetime import date
from app import app, db, DailyBriefing
from ai_briefing import generate_daily_briefing


with app.app_context():

    today = date.today()

    # Vérifier si déjà généré aujourd'hui
    existing = DailyBriefing.query.filter_by(date=today).first()

    if existing:
        print("⚠️ Briefing déjà généré aujourd'hui")
    else:
        # Données (temporaire)
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

        # Générer avec IA
        print("⏳ Génération du briefing...")
        briefing = generate_daily_briefing(btc_data, gold_data, eco_data)

        # Sauvegarde
        new_briefing = DailyBriefing(
            date=today,
            content=briefing
        )

        db.session.add(new_briefing)
        db.session.commit()

        print("✅ Briefing enregistré en base")