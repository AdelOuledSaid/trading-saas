from app.extensions import db


# =========================
# USER (si pas déjà ailleurs)
# =========================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    plan = db.Column(db.String(20), default="basic")


# =========================
# WATCHLIST VIP
# =========================
class UserWatchlist(db.Model):
    __tablename__ = "user_watchlist"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    coin_id = db.Column(db.String(80), nullable=False)
    symbol = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    image = db.Column(db.String(300))

    created_at = db.Column(db.DateTime, server_default=db.func.now())

    user = db.relationship("User", backref=db.backref("watchlist_items", lazy=True))