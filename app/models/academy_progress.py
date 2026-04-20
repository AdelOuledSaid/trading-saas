from datetime import datetime

from app.extensions import db


class AcademyProgress(db.Model):
    __tablename__ = "academy_progress"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True)

    level1 = db.Column(db.Integer, default=0, nullable=False)
    level2 = db.Column(db.Integer, default=0, nullable=False)
    level3 = db.Column(db.Integer, default=0, nullable=False)
    level4 = db.Column(db.Integer, default=0, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    user = db.relationship("User", backref=db.backref("academy_progress_rel", uselist=False))