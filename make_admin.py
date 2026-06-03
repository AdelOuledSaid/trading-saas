from app import create_app
from models import db, User

EMAIL = "adelouledsaid6@gmail.com"

app = create_app()

with app.app_context():
    u = User.query.filter_by(email=EMAIL).first()

    if not u:
        print("Utilisateur introuvable :", EMAIL)
    else:
        u.is_admin = True
        db.session.commit()
        print("OK admin activé pour :", u.email)
        print("is_admin =", u.is_admin)