from datetime import datetime
from flask_login import UserMixin
from app.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)

    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password = db.Column(db.String(255), nullable=False)

    # Subscription
    is_premium = db.Column(db.Boolean, default=False, nullable=False)
    plan = db.Column(db.String(20), default="free", nullable=False, index=True)

    # Stripe
    stripe_customer_id = db.Column(db.String(255), unique=True, nullable=True)
    stripe_subscription_id = db.Column(db.String(255), unique=True, nullable=True)

    # Admin
    is_admin = db.Column(db.Boolean, default=False, nullable=False)

    # Dates
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<User {self.email} plan={self.plan}>"