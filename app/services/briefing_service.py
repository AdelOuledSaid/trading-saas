from datetime import datetime
from flask import current_app

from app.extensions import db
from app.models import DailyBriefing
from app.services.market_service import get_btc_data, get_gold_data, get_economic_calendar
from ai_briefing import generate_daily_briefing


def ensure_daily_briefing():
    today = datetime.utcnow().date()
    existing = DailyBriefing.query.filter_by(date=today).first()

    if existing:
        return existing

    try:
        btc_data = get_btc_data()
        gold_data = get_gold_data()
        eco_data = get_economic_calendar()

        content = generate_daily_briefing(btc_data, gold_data, eco_data)

        briefing = DailyBriefing(
            date=today,
            content=content
        )

        db.session.add(briefing)
        db.session.commit()
        current_app.logger.info("Briefing du jour généré automatiquement.")
        return briefing

    except Exception as e:
        current_app.logger.error("Erreur génération briefing: %s", repr(e))
        return None