import json
from pathlib import Path

try:
    from deep_translator import GoogleTranslator
except ImportError:
    raise SystemExit("Installe deep-translator: pip install deep-translator")

POSSIBLE_DIRS = [
    Path("app/translations"),
    Path("translations"),
]

TRANSLATIONS_DIR = None
for d in POSSIBLE_DIRS:
    if (d / "fr.json").exists():
        TRANSLATIONS_DIR = d
        break

if TRANSLATIONS_DIR is None:
    raise SystemExit("fr.json introuvable. Mets ce script à la racine du projet ou vérifie app/translations/fr.json")

TARGETS = ["en", "es", "it", "de", "pt", "ru"]

PREFIXES = (
    "markets_crypto_",
    "markets_economic_calendar_",
    "markets_forex_",
    "markets_liquidations_",
    "markets_open_interest_",
    "markets_opportunites_",
    "markets_sentiment_",
    "markets_token_unlocks_",
    "markets_whales_",
)

def load(path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}

def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def main():
    print(f"[INFO] Dossier traductions utilisé: {TRANSLATIONS_DIR}")
    fr = load(TRANSLATIONS_DIR / "fr.json")
    if not fr:
        raise SystemExit("fr.json vide ou introuvable")

    for lang in TARGETS:
        path = TRANSLATIONS_DIR / f"{lang}.json"
        data = load(path)
        translator = GoogleTranslator(source="fr", target=lang)
        count = 0

        print(f"\n[INFO] Traduction Markets -> {lang}")
        for key, fr_value in fr.items():
            if not key.startswith(PREFIXES):
                continue
            if not isinstance(fr_value, str) or not fr_value.strip():
                continue

            current = data.get(key, "")
            if not current or current == fr_value:
                try:
                    data[key] = translator.translate(fr_value)
                    count += 1
                    print("OK", key)
                except Exception as e:
                    print("WARN", key, e)
                    data[key] = fr_value

        save(path, data)
        print(f"[DONE] {lang}: {count} clés traduites")

    print("\n✅ Traductions Markets terminées.")

if __name__ == "__main__":
    main()
