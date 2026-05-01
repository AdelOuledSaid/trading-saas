from datetime import datetime
from app.extensions import db


class TokenUnlockEvent(db.Model):
    __tablename__ = "token_unlock_events"

    id = db.Column(db.Integer, primary_key=True)

    symbol = db.Column(db.String(32), nullable=False, index=True)
    token = db.Column(db.String(64), nullable=True)
    name = db.Column(db.String(128), nullable=True)

    unlock_date = db.Column(db.Date, nullable=False, index=True)

    value_usd = db.Column(db.Float, default=0)
    market_cap_usd = db.Column(db.Float, default=0)
    market_cap_ratio = db.Column(db.Float, default=0)

    risk_level = db.Column(db.String(32), default="low", index=True)
    signal_level = db.Column(db.String(32), default="watch", index=True)

    source = db.Column(db.String(64), default="real")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("symbol", "unlock_date", name="uq_token_unlock_symbol_date"),
    )
