import json
import sys
from datetime import datetime

import requests
import os
from dotenv import load_dotenv

load_dotenv()

SECRET = os.getenv("MANUAL_SIGNAL_SECRET")
# =========================
# CONFIG
# =========================
API_BASE_URL = "http://127.0.0.1:5000"


DEFAULT_TIMEOUT = 20
ALLOWED_EVENTS = {"TP", "SL"}


# =========================
# HELPERS
# =========================
def print_header():
    print("=" * 72)
    print("VELWOLF IA SIGNAL ")
    print("=" * 72)


def ask_signal_id() -> int:
    while True:
        raw = input("Signal ID à fermer: ").strip()
        try:
            signal_id = int(raw)
            if signal_id <= 0:
                print("Le signal ID doit être > 0.")
                continue
            return signal_id
        except ValueError:
            print("Signal ID invalide.")


def ask_event() -> str:
    while True:
        event = input("Résultat (TP/SL): ").strip().upper()
        if event in ALLOWED_EVENTS:
            return event
        print("Valeur invalide. Utilise TP ou SL.")


def build_request():
    signal_id = ask_signal_id()
    event = ask_event()

    print("\nRésumé fermeture")
    print("-" * 72)
    print(f"Signal ID : {signal_id}")
    print(f"Résultat  : {event}")
    print("-" * 72)

    confirm = input("Confirmer fermeture ? (y/n): ").strip().lower()
    if confirm not in {"y", "yes", "o", "oui"}:
        print("Fermeture annulée.")
        sys.exit(0)

    url = f"{API_BASE_URL}/api/manual-signal/{signal_id}/close"
    payload = {
        "secret": SECRET,
        "event": event,
    }

    return url, payload


def close_signal(url: str, payload: dict):
    started_at = datetime.utcnow()

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=DEFAULT_TIMEOUT,
        )
    except requests.RequestException as exc:
        print(f"\nErreur réseau: {exc}")
        sys.exit(1)

    ended_at = datetime.utcnow()
    latency_ms = int((ended_at - started_at).total_seconds() * 1000)

    print("\nRéponse serveur")
    print("-" * 72)
    print(f"Status code : {response.status_code}")
    print(f"Latency     : {latency_ms} ms")

    try:
        data = response.json()
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception:
        print(response.text)

    if response.status_code not in {200, 201}:
        sys.exit(1)


def main():
    print_header()
    url, payload = build_request()
    close_signal(url, payload)


if __name__ == "__main__":
    main()