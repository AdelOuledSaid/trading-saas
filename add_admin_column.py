import sqlite3

conn = sqlite3.connect("instance/users.db")
cursor = conn.cursor()

# Vérifie les colonnes existantes
cursor.execute("PRAGMA table_info(user)")
columns = [col[1] for col in cursor.fetchall()]

# Ajoute la colonne si elle n'existe pas
if "is_admin" not in columns:
    cursor.execute("ALTER TABLE user ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0")
    print("✅ Colonne is_admin ajoutée")
else:
    print("⚠️ Colonne is_admin déjà existante")

conn.commit()
conn.close()

print("✅ Terminé")