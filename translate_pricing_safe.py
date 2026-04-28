import json
from pathlib import Path
from deep_translator import GoogleTranslator

langs = ["en","es","it","de","pt","ru"]

def load(p): return json.loads(p.read_text(encoding="utf-8"))
def save(p,d): p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")

translations = Path("app/translations")
fr = load(translations/"fr.json")

for lang in langs:
    data = load(translations/f"{lang}.json")
    tr = GoogleTranslator(source="fr", target=lang)

    for k,v in fr.items():
        if k not in data or data[k]==v:
            try:
                data[k] = tr.translate(v)
            except:
                pass

    save(translations/f"{lang}.json",data)

print("DONE SAFE")
