import os
import re

TEMPLATES_DIR = "app/templates"

def generate_key(text):
    key = text.lower()
    key = re.sub(r'[^a-z0-9 ]', '', key)
    key = key.replace(" ", "_")
    return key[:40]

def process_file(path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # détecte texte entre balises HTML
    matches = re.findall(r'>([^<>{}]{5,})<', content)

    for m in matches:
        text = m.strip()

        if "{{" in text or "t(" in text:
            continue

        key = generate_key(text)

        new = f'{{{{ t("{key}", "{text}") }}}}'
        content = content.replace(f">{text}<", f">{new}<")

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def main():
    for root, _, files in os.walk(TEMPLATES_DIR):
        for file in files:
            if file.endswith(".html"):
                process_file(os.path.join(root, file))

    print("✅ Tous les templates corrigés automatiquement")

if __name__ == "__main__":
    main()