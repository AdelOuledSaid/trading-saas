import json
import re
from pathlib import Path

LANGS = ["fr", "en", "es", "it", "de", "pt", "ru"]
TARGET_LANGS = ["en", "es", "it", "de", "pt", "ru"]

# Clés à ignorer si tu veux limiter plus tard
IGNORE_PREFIXES = ()

# Dossiers possibles
TEMPLATES_DIRS = [
    Path("app/templates"),
    Path("templates"),
]

TRANSLATIONS_DIRS = [
    Path("app/translations"),
    Path("translations"),
]

def find_existing_dir(possible_dirs, required_file=None):
    for d in possible_dirs:
        if d.exists() and d.is_dir():
            if required_file is None or (d / required_file).exists():
                return d
    return None

def load_json(path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}

def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def extract_t_keys_from_template(text):
    """
    Extrait uniquement les t("key", "fallback") / t('key', 'fallback').
    Ne touche pas au HTML, ne casse pas les pages.
    """
    keys = {}

    pattern = re.compile(
        r"""t\(\s*['"]([^'"]+)['"]\s*,\s*(['"])(.*?)\2\s*\)""",
        re.S
    )

    for m in pattern.finditer(text):
        key = m.group(1).strip()
        fallback = m.group(3).replace('\\"', '"').replace("\\'", "'")
        fallback = " ".join(fallback.split())

        if not key or key.startswith(IGNORE_PREFIXES):
            continue

        keys[key] = fallback

    return keys

def scan_templates(templates_dir):
    all_keys = {}
    file_report = {}

    html_files = list(templates_dir.rglob("*.html"))
    for path in html_files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        keys = extract_t_keys_from_template(text)
        all_keys.update(keys)
        file_report[str(path)] = len(keys)

    return all_keys, file_report

def translate_missing(translations_dir, fr_data):
    try:
        from deep_translator import GoogleTranslator
    except ImportError:
        print("\n[INFO] deep-translator non installé.")
        print("Pour traduire automatiquement:")
        print("pip install deep-translator")
        return {}

    translate_report = {}

    for lang in TARGET_LANGS:
        path = translations_dir / f"{lang}.json"
        data = load_json(path)
        translator = GoogleTranslator(source="fr", target=lang)
        count = 0
        skipped = 0
        failed = 0

        print(f"\n[INFO] Traduction manquante -> {lang}")

        for key, fr_value in fr_data.items():
            if not isinstance(fr_value, str) or not fr_value.strip():
                continue

            current = data.get(key, "")

            # Sécurité: ne jamais écraser une vraie traduction existante
            if current and current != fr_value:
                skipped += 1
                continue

            try:
                data[key] = translator.translate(fr_value)
                count += 1
                print("OK", key)
            except Exception as e:
                failed += 1
                data[key] = fr_value
                print("WARN", key, e)

        save_json(path, data)
        translate_report[lang] = {
            "translated": count,
            "skipped_existing": skipped,
            "failed": failed,
        }

    return translate_report

def main():
    templates_dir = find_existing_dir(TEMPLATES_DIRS)
    translations_dir = find_existing_dir(TRANSLATIONS_DIRS, "fr.json")

    if not templates_dir:
        raise SystemExit("Dossier templates introuvable. Vérifie app/templates ou templates.")
    if not translations_dir:
        raise SystemExit("Dossier translations introuvable. Vérifie app/translations/fr.json ou translations/fr.json.")

    print(f"[INFO] Templates: {templates_dir}")
    print(f"[INFO] Translations: {translations_dir}")

    template_keys, file_report = scan_templates(templates_dir)
    print(f"[INFO] Clés t(...) trouvées dans les templates: {len(template_keys)}")

    # Charge JSON actuels
    translations = {lang: load_json(translations_dir / f"{lang}.json") for lang in LANGS}

    # 1) Complète fr.json avec tous les fallbacks
    fr = translations.get("fr", {})
    fr_added = 0

    for key, fallback in template_keys.items():
        if key not in fr or not fr.get(key):
            fr[key] = fallback
            fr_added += 1

    save_json(translations_dir / "fr.json", fr)

    # 2) Complète toutes les langues avec fallback FR si clé manquante
    lang_report = {}
    for lang in TARGET_LANGS:
        data = translations.get(lang, {})
        added = 0
        same_as_fr = 0

        for key in template_keys:
            fr_value = fr.get(key, template_keys[key])

            if key not in data or not data.get(key):
                data[key] = fr_value
                added += 1

            if data.get(key) == fr_value:
                same_as_fr += 1

        save_json(translations_dir / f"{lang}.json", data)

        lang_report[lang] = {
            "added_missing_keys": added,
            "keys_still_equal_to_fr": same_as_fr,
            "final_keys": len(data),
        }

    # 3) Rapport
    report = {
        "templates_dir": str(templates_dir),
        "translations_dir": str(translations_dir),
        "template_keys_found": len(template_keys),
        "fr_added": fr_added,
        "languages": lang_report,
        "files_scanned": file_report,
    }

    Path("translation_repair_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("\n[DONE] Réparation des clés terminée.")
    print(f"[INFO] Clés ajoutées dans fr.json: {fr_added}")
    print("[INFO] Rapport: translation_repair_report.json")

    need_translation = any(v["keys_still_equal_to_fr"] > 0 for v in lang_report.values())
    if need_translation:
        print("\n[INFO] Certaines clés sont encore en français dans les autres langues.")
        answer = input("Traduire automatiquement maintenant ? (y/n): ").strip().lower()
        if answer == "y":
            tr_report = translate_missing(translations_dir, fr)
            report["auto_translation"] = tr_report
            Path("translation_repair_report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            print("\n[DONE] Traduction automatique terminée.")
        else:
            print("\n[INFO] Tu peux relancer ce script plus tard et répondre y.")

if __name__ == "__main__":
    main()
