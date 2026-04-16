import json
import os

SUPPORTED_LANGS = ["fr", "en", "es"]
DEFAULT_LANG = "fr"

# cache pour éviter de recharger les fichiers à chaque requête
_translation_cache = {}


def load_translations(lang):
    """
    Charge les traductions avec cache
    """
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG

    # cache
    if lang in _translation_cache:
        return _translation_cache[lang]

    base_dir = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(base_dir, "translations", f"{lang}.json")

    if not os.path.exists(path):
        path = os.path.join(base_dir, "translations", f"{DEFAULT_LANG}.json")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            _translation_cache[lang] = data
            return data
    except Exception:
        return {}


def translate(translations, key, fallback=None):
    """
    Fonction safe pour traduire
    """
    if not translations:
        return fallback or key

    return translations.get(key, fallback or key)