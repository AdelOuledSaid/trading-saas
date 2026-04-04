from datetime import datetime
from app.extensions import db


class Signal(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    trade_id = db.Column(db.String(120), unique=True, nullable=True, index=True)

    asset = db.Column(db.String(50), nullable=False)
    action = db.Column(db.String(10), nullable=False)

    entry_price = db.Column(db.Float, nullable=False)
    stop_loss = db.Column(db.Float, nullable=True)
    take_profit = db.Column(db.Float, nullable=True)

    status = db.Column(db.String(20), default="OPEN", nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    closed_at = db.Column(db.DateTime, nullable=True)