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

    # Premium fields
    confidence = db.Column(db.Float, default=0.0, nullable=False)
    reason = db.Column(db.Text, nullable=True)

    timeframe = db.Column(db.String(20), nullable=True)   # M5, M15, H1, H4...
    signal_type = db.Column(db.String(100), default="intraday", nullable=False)

    market_trend = db.Column(db.String(20), nullable=True)  # bullish / bearish / neutral

    risk_reward = db.Column(db.Float, nullable=True)
    result_percent = db.Column(db.Float, nullable=True)

    is_public = db.Column(db.Boolean, default=True, nullable=False)
    source = db.Column(db.String(50), default="system", nullable=False)
    news_sentiment = db.Column(db.Float, nullable=True)

    replay = db.relationship(
        "TradeReplay",
        backref="signal",
        uselist=False,
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Signal {self.asset} {self.action} {self.status}>"

    def compute_rr(self):
        if self.stop_loss is None or self.take_profit is None or self.entry_price is None:
            return None

        risk = abs(self.entry_price - self.stop_loss)
        reward = abs(self.take_profit - self.entry_price)

        if risk == 0:
            return None

        return round(reward / risk, 2)

    def update_risk_reward(self):
        self.risk_reward = self.compute_rr()

    def confidence_label(self):
        if self.confidence >= 80:
            return "High Probability"
        if self.confidence >= 60:
            return "Strong Setup"
        return "Standard"