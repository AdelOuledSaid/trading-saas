import json
from pathlib import Path
try:
    from deep_translator import GoogleTranslator
except ImportError:
    raise SystemExit("Installe deep-translator: pip install deep-translator")

dirs=[Path("app/translations"), Path("translations")]
tdir=next((d for d in dirs if (d/"fr.json").exists()), None)
if not tdir:
    raise SystemExit("fr.json introuvable. Mets ce script à la racine du projet.")
targets=["en","es","it","de","pt","ru"]
prefixes=("lab_psychology_","lab_risk_","lab_structure_","lab_index_")

def load(p): return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
def save(p,d): p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")
fr=load(tdir/"fr.json")
for lang in targets:
    data=load(tdir/f"{lang}.json")
    translator=GoogleTranslator(source="fr", target=lang)
    count=0
    print(f"\n[INFO] Traduction Lab -> {lang}")
    for k,v in fr.items():
        if not k.startswith(prefixes) or not isinstance(v,str) or not v.strip():
            continue
        if not data.get(k) or data.get(k)==v:
            try:
                data[k]=translator.translate(v); count+=1; print("OK",k)
            except Exception as e:
                print("WARN",k,e); data[k]=v
    save(tdir/f"{lang}.json",data)
    print(f"[DONE] {lang}: {count} clés traduites")
print("\n✅ Traductions Trading Lab terminées.")
