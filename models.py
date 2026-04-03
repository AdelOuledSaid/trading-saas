from datetime import datetime
from flask_login import UserMixin
from extensions import db


class DailyBriefing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=True, nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)

    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)

    is_premium = db.Column(db.Boolean, default=False, nullable=False)
    plan = db.Column(db.String(20), default="free", nullable=False)

    stripe_customer_id = db.Column(db.String(255), nullable=True)
    stripe_subscription_id = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


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