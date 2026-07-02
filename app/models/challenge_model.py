from datetime import datetime

from app.extensions import db


class ChallengeScore(db.Model):
    """Public 'Défi Trading' leaderboard entry (guest-friendly, no account needed)."""

    __tablename__ = "challenge_score"

    id = db.Column(db.Integer, primary_key=True)
    pseudo = db.Column(db.String(40), nullable=False, index=True)
    score = db.Column(db.Integer, nullable=False, default=0, index=True)
    rounds = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def to_public_dict(self):
        return {
            "pseudo": self.pseudo,
            "score": self.score,
            "rounds": self.rounds,
        }

    def __repr__(self):
        return f"<ChallengeScore {self.pseudo} {self.score}>"
