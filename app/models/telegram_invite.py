from datetime import datetime
from app.extensions import db


class TelegramInvite(db.Model):
    __tablename__ = "telegram_invite"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    plan = db.Column(db.String(20), nullable=False, index=True)
    chat_id = db.Column(db.String(64), nullable=False, index=True)
    invite_link = db.Column(db.Text, nullable=False, unique=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=True, index=True)

    is_revoked = db.Column(db.Boolean, default=False, nullable=False, index=True)
    revoked_at = db.Column(db.DateTime, nullable=True)

    # optionnel mais très utile
    telegram_user_id = db.Column(db.String(64), nullable=True, index=True)
    note = db.Column(db.String(255), nullable=True)

    user = db.relationship("User", backref=db.backref("telegram_invites", lazy=True, cascade="all, delete-orphan"))

    def __repr__(self):
        return (
            f"<TelegramInvite id={self.id} user_id={self.user_id} "
            f"plan={self.plan} revoked={self.is_revoked}>"
        )

    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        return datetime.utcnow() >= self.expires_at