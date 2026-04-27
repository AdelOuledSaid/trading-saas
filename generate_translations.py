import json
import os
from deep_translator import GoogleTranslator

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRANSLATIONS_DIR = os.path.join(BASE_DIR, "app", "translations")

SOURCE_LANG = "fr"
SOURCE_FILE = os.path.join(TRANSLATIONS_DIR, "fr.json")

TARGET_LANGS = {
    "en": "en",
    "es": "es",
    "it": "it",
    "de": "de",
    "pt": "pt",
    "ru": "ru",
}


def load_json(path):
    if not os.path.exists(path):
        return {}

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def translate_text(text, target_lang):
    if not isinstance(text, str) or not text.strip():
        return text

    try:
        return GoogleTranslator(source=SOURCE_LANG, target=target_lang).translate(text)
    except Exception as e:
        print(f"[WARN] Traduction échouée: {text} -> {e}")
        return text


def generate_language(source_data, lang_code, target_lang):
    print(f"\n[INFO] Mise à jour {lang_code}.json...")

    output_path = os.path.join(TRANSLATIONS_DIR, f"{lang_code}.json")
    existing_data = load_json(output_path)

    updated = dict(existing_data)

    for key, french_value in source_data.items():
        if key not in updated or not str(updated.get(key, "")).strip():
            updated[key] = translate_text(french_value, target_lang)
            print(f"OK {lang_code}: {key}")
        else:
            print(f"SKIP {lang_code}: {key}")

    save_json(output_path, updated)
    print(f"[DONE] {output_path}")


def main():
    if not os.path.exists(SOURCE_FILE):
        raise FileNotFoundError(f"Fichier introuvable: {SOURCE_FILE}")

    source_data = load_json(SOURCE_FILE)

    for lang_code, target_lang in TARGET_LANGS.items():
        generate_language(source_data, lang_code, target_lang)

    print("\n✅ Traductions générées depuis fr.json.")


if __name__ == "__main__":
    main()