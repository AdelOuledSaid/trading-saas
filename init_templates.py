import os

# =========================
# STRUCTURE
# =========================
structure = {
    "templates/signals": [
        "index.html",
        "btc.html",
        "eth.html",
        "gold.html",
        "us100.html",
        "history.html",
    ],
    "templates/trading_lab": [
        "index.html",
        "structure.html",
        "risk.html",
        "psychology.html",
    ],
}

# =========================
# CONTENU DE BASE
# =========================
base_html = """{% include "partials/navbar.html" %}

<section class="inner-hero">
    <div class="section-container">
        <h1>Page en construction</h1>
        <p>Cette page sera bientôt remplie avec du contenu premium.</p>
    </div>
</section>
"""

# =========================
# CREATION
# =========================
for folder, files in structure.items():
    os.makedirs(folder, exist_ok=True)
    print(f"📁 Dossier créé : {folder}")

    for file in files:
        path = os.path.join(folder, file)

        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(base_html)
            print(f"   ✅ Fichier créé : {path}")
        else:
            print(f"   ⚠️ Existe déjà : {path}")

print("\n🚀 Structure templates créée avec succès !")