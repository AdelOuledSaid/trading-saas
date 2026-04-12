from sqlalchemy import text

from app import create_app
from app.extensions import db

app = create_app()

with app.app_context():
    try:
        db.session.execute(text('ALTER TABLE "user" ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE;'))
        db.session.commit()
        print("✅ Colonne is_admin ajoutée dans PostgreSQL")
    except Exception as e:
        db.session.rollback()
        print(f"⚠️ Peut-être déjà existante ou autre erreur : {e}")