from datetime import datetime
from app.extensions import db


class DailyBriefing(db.Model):
    __tablename__ = "daily_briefing"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=True, nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<DailyBriefing {self.date}>"