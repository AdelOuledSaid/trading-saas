from datetime import datetime

from app.extensions import db


class TelegramDispatchLog(db.Model):
    __tablename__ = "telegram_dispatch_logs"

    id = db.Column(db.Integer, primary_key=True)

    content_type = db.Column(db.String(50), nullable=False, index=True)
    tier = db.Column(db.String(20), nullable=False, index=True)

    dedup_key = db.Column(db.String(255), nullable=False, unique=True, index=True)

    content_hash = db.Column(db.String(64), nullable=True, index=True)
    content_ref = db.Column(db.String(255), nullable=True, index=True)

    sent_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="sent")

    def __repr__(self):
        return (
            f"<TelegramDispatchLog id={self.id} "
            f"type={self.content_type} tier={self.tier} key={self.dedup_key}>"
        )