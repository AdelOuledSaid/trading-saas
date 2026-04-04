from app.extensions import db
from app.models import User


def load_user(user_id):
    return db.session.get(User, int(user_id))