import json, re
from pathlib import Path
from deep_translator import GoogleTranslator

FILES = ["about.html", "privacy.html"]
TARGETS = ["en", "es", "it", "de", "pt", "ru"]

def load(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

def save(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def find_dir(paths, required=None):
    for p in paths:
        if p.exists() and p.is_dir() and (required is None or (p / required).exists()):
            return p
    return None

def extract(text):
    out = {}
    pat = re.compile(r"""t\(\s*['"]([^'"]+)['"]\s*,\s*(['"])(.*?)\2\s*\)""", re.S)
    for m in pat.finditer(text):
        out[m.group(1)] = " ".join(m.group(3).replace('\\\"', '"').replace("\\'", "'").split())
    return out

templates = find_dir([Path("templates"), Path("app/templates")])
translations = find_dir([Path("app/translations"), Path("translations")], "fr.json")

if not templates:
    raise SystemExit("Dossier templates introuvable")
if not translations:
    raise SystemExit("Dossier app/translations introuvable")

keys = {}
for f in FILES:
    matches = list(templates.rglob(f))
    if not matches:
        print("WARN fichier introuvable:", f)
        continue
    keys.update(extract(matches[0].read_text(encoding="utf-8", errors="ignore")))

fr = load(translations / "fr.json")
for k, v in keys.items():
    if not fr.get(k):
        fr[k] = v
save(translations / "fr.json", fr)

for lang in TARGETS:
    data = load(translations / f"{lang}.json")
    tr = GoogleTranslator(source="fr", target=lang)
    translated = skipped = failed = 0

    print("\n[INFO] About/Privacy ->", lang)

    for k in keys:
        fr_val = fr.get(k, keys[k])
        cur = data.get(k, "")

        if cur and cur != fr_val:
            skipped += 1
            continue

        try:
            data[k] = tr.translate(fr_val)
            translated += 1
        except Exception:
            data[k] = fr_val
            failed += 1

    save(translations / f"{lang}.json", data)
    print("[DONE]", lang, "translated=", translated, "skipped=", skipped, "failed=", failed)

print("\nDONE SAFE")
