from datetime import datetime
from app import app, db, DailyBriefing

with app.app_context():
    today = datetime.utcnow().date()
    briefing = DailyBriefing.query.filter_by(date=today).first()

    if briefing:
        db.session.delete(briefing)
        db.session.commit()
        print("✅ Briefing du jour supprimé")
    else:
        print("Aucun briefing du jour à supprimer")