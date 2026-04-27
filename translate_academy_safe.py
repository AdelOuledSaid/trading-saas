import json
from pathlib import Path

try:
    from deep_translator import GoogleTranslator
except ImportError:
    raise SystemExit("Installe deep-translator: pip install deep-translator")

dirs = [Path("app/translations"), Path("translations")]
tdir = next((d for d in dirs if (d / "fr.json").exists()), None)
if not tdir:
    raise SystemExit("fr.json introuvable. Lance ce script à la racine du projet.")

targets = ["en", "es", "it", "de", "pt", "ru"]
prefixes = ("academy_", "current_progress", "context", "structure", "risk", "exit")

def load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

fr = load(tdir / "fr.json")

for lang in targets:
    data = load(tdir / f"{lang}.json")
    translator = GoogleTranslator(source="fr", target=lang)
    count = 0
    print(f"\n[INFO] Traduction Academy -> {lang}")

    for key, fr_value in fr.items():
        if not key.startswith(prefixes):
            continue
        if not isinstance(fr_value, str) or not fr_value.strip():
            continue

        current = data.get(key, "")
        if current and current != fr_value:
            continue

        try:
            data[key] = translator.translate(fr_value)
            count += 1
            print("OK", key)
        except Exception as e:
            print("WARN", key, e)
            data[key] = fr_value

    save(tdir / f"{lang}.json", data)
    print(f"[DONE] {lang}: {count} clés traduites")

print("\n✅ Academy traduite sans écraser tes traductions existantes.")
