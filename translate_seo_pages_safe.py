import json, re
from pathlib import Path

try:
    from deep_translator import GoogleTranslator
except ImportError:
    raise SystemExit("Installe deep-translator: pip install deep-translator")

FILES = [
    "analyse_bitcoin.html", "analyse_crypto.html", "crypto_signals.html",
    "resultats_trading.html", "signaux_trading.html", "trading_academy.html"
]
TARGETS = ["en", "es", "it", "de", "pt", "ru"]

def find_dir(options, required=None):
    for d in options:
        if d.exists() and d.is_dir() and (required is None or (d / required).exists()):
            return d
    return None

def load(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

def save(p, d):
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

def keys_from(text):
    out = {}
    pat = re.compile(r"""t\(\s*['"]([^'"]+)['"]\s*,\s*(['"])(.*?)\2\s*\)""", re.S)
    for m in pat.finditer(text):
        key = m.group(1).strip()
        val = " ".join(m.group(3).replace('\\"', '"').replace("\\'", "'").split())
        if key:
            out[key] = val
    return out

templates = find_dir([Path("templates"), Path("app/templates")])
translations = find_dir([Path("app/translations"), Path("translations")], "fr.json")
if not templates:
    raise SystemExit("Dossier templates introuvable.")
if not translations:
    raise SystemExit("Dossier app/translations introuvable.")

seo_keys = {}
for fname in FILES:
    found = list(templates.rglob(fname))
    if not found:
        print("WARN introuvable:", fname)
        continue
    seo_keys.update(keys_from(found[0].read_text(encoding="utf-8", errors="ignore")))

fr = load(translations / "fr.json")
for k, v in seo_keys.items():
    if not fr.get(k):
        fr[k] = v
save(translations / "fr.json", fr)

for lang in TARGETS:
    data = load(translations / f"{lang}.json")
    translator = GoogleTranslator(source="fr", target=lang)
    translated = skipped = failed = 0
    print(f"\n[INFO] SEO pages -> {lang}")

    for k in seo_keys:
        fr_val = fr.get(k, seo_keys[k])
        current = data.get(k, "")

        # sécurité: ne jamais écraser une vraie traduction existante
        if current and current != fr_val:
            skipped += 1
            continue

        try:
            data[k] = translator.translate(fr_val)
            translated += 1
            print("OK", k)
        except Exception as e:
            data[k] = fr_val
            failed += 1
            print("WARN", k, e)

    save(translations / f"{lang}.json", data)
    print(f"[DONE] {lang}: translated={translated}, skipped={skipped}, failed={failed}")

print("\n✅ SEO pages traduites sans écraser l'existant.")
