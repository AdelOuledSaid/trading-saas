import json
import os

SUPPORTED_LANGS = ["en", "fr", "es", "it", "de", "pt", "ru"]
DEFAULT_LANG = "en"

_translation_cache = {}


def load_translations(lang):
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG

    if lang in _translation_cache:
        return _translation_cache[lang]

    base_dir = os.path.dirname(os.path.dirname(__file__))
    translations_dir = os.path.join(base_dir, "translations")

    default_path = os.path.join(translations_dir, f"{DEFAULT_LANG}.json")
    lang_path = os.path.join(translations_dir, f"{lang}.json")

    default_data = {}
    lang_data = {}

    try:
        if os.path.exists(default_path):
            with open(default_path, "r", encoding="utf-8") as f:
                default_data = json.load(f)
    except Exception:
        default_data = {}

    try:
        if os.path.exists(lang_path):
            with open(lang_path, "r", encoding="utf-8") as f:
                lang_data = json.load(f)
    except Exception:
        lang_data = {}

    # Merge intelligent :
    # si une clé manque dans la langue choisie, on garde l'anglais
    data = {**default_data, **lang_data}

    _translation_cache[lang] = data
    return data


def translate(translations, key, fallback=None):
    if not key:
        return fallback or ""

    if not translations:
        return fallback or key.replace("_", " ").capitalize()

    value = translations.get(key)

    if value:
        return value

    if fallback:
        return fallback

    return key.replace("_", " ").capitalize()


def clear_translation_cache():
    _translation_cache.clear()