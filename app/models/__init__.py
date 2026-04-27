from app.models.user import User
from app.models.signal import Signal
from app.models.briefing import DailyBriefing
from app.models.telegram_invite import TelegramInvite
from app.models.replay import (
    TradeReplay,
    ReplayCandle,
    ReplayEvent,
    UserReplayDecision
)

from app.models.telegram_dispatch_log import TelegramDispatchLog

from app.extensions import db


class UserWatchlist(db.Model):
    __tablename__ = "user_watchlist"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    coin_id = db.Column(db.String(80), nullable=False)
    symbol = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    image = db.Column(db.String(300), nullable=True)

    created_at = db.Column(db.DateTime, server_default=db.func.now())