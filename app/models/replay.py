from datetime import datetime

from app.extensions import db


class TradeReplay(db.Model):
    __tablename__ = "trade_replays"

    id = db.Column(db.Integer, primary_key=True)

    signal_id = db.Column(db.Integer, db.ForeignKey("signal.id"), nullable=False, index=True)
    symbol = db.Column(db.String(30), nullable=False)
    timeframe = db.Column(db.String(20), nullable=False)
    direction = db.Column(db.String(10), nullable=False)

    replay_start = db.Column(db.DateTime, nullable=False)
    replay_end = db.Column(db.DateTime, nullable=False)

    entry_time = db.Column(db.DateTime, nullable=False)
    exit_time = db.Column(db.DateTime, nullable=True)

    entry_price = db.Column(db.Float, nullable=False)
    stop_loss = db.Column(db.Float, nullable=True)
    take_profit = db.Column(db.Float, nullable=True)

    result = db.Column(db.String(20), nullable=True)   # WIN / LOSS / BREAKEVEN / OPEN
    result_percent = db.Column(db.Float, nullable=True)

    market_context = db.Column(db.Text, nullable=True)
    post_analysis = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    candles = db.relationship(
        "ReplayCandle",
        backref="trade_replay",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="ReplayCandle.position_index.asc()"
    )

    events = db.relationship(
        "ReplayEvent",
        backref="trade_replay",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="ReplayEvent.position_index.asc()"
    )

    decisions = db.relationship(
        "UserReplayDecision",
        backref="trade_replay",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="UserReplayDecision.created_at.desc()"
    )

    def __repr__(self):
        return f"<TradeReplay {self.symbol} {self.timeframe} {self.direction}>"


class ReplayCandle(db.Model):
    __tablename__ = "replay_candles"

    id = db.Column(db.Integer, primary_key=True)

    trade_replay_id = db.Column(
        db.Integer,
        db.ForeignKey("trade_replays.id"),
        nullable=False,
        index=True
    )

    candle_time = db.Column(db.DateTime, nullable=False, index=True)
    open = db.Column(db.Float, nullable=False)
    high = db.Column(db.Float, nullable=False)
    low = db.Column(db.Float, nullable=False)
    close = db.Column(db.Float, nullable=False)
    volume = db.Column(db.Float, nullable=True)

    position_index = db.Column(db.Integer, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<ReplayCandle replay_id={self.trade_replay_id} index={self.position_index}>"


class ReplayEvent(db.Model):
    __tablename__ = "replay_events"

    id = db.Column(db.Integer, primary_key=True)

    trade_replay_id = db.Column(
        db.Integer,
        db.ForeignKey("trade_replays.id"),
        nullable=False,
        index=True
    )

    event_time = db.Column(db.DateTime, nullable=False, index=True)
    event_type = db.Column(db.String(30), nullable=False)   # entry, warning, tp_hit, sl_hit...
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)

    price_level = db.Column(db.Float, nullable=True)
    position_index = db.Column(db.Integer, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<ReplayEvent {self.event_type} replay_id={self.trade_replay_id} index={self.position_index}>"


class UserReplayDecision(db.Model):
    __tablename__ = "user_replay_decisions"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    trade_replay_id = db.Column(
        db.Integer,
        db.ForeignKey("trade_replays.id"),
        nullable=False,
        index=True
    )

    decision = db.Column(db.String(20), nullable=False)   # close / hold / partial
    score = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(30), nullable=True)      # good / medium / bad
    feedback = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return (
            f"<UserReplayDecision user_id={self.user_id} "
            f"replay_id={self.trade_replay_id} decision={self.decision} score={self.score}>"
        )