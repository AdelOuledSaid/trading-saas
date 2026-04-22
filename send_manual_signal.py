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
API_ENDPOINT = f"{API_BASE_URL}/api/manual-signal"


DEFAULT_TIMEOUT = 20

ALLOWED_ASSETS = {
    "BTCUSD",
    "ETHUSD",
    "SOLUSD",
    "XRPUSD",
    "GOLD",
    "US100",
    "US500",
    "FRA40",
}

ALLOWED_ACTIONS = {"BUY", "SELL"}


# =========================
# HELPERS
# =========================
def print_header():
    print("=" * 72)
    print("VELWOLF IA SIGNAL")
    print("=" * 72)


def safe_float_input(label: str) -> float:
    while True:
        value = input(f"{label}: ").strip().replace(",", ".")
        try:
            number = float(value)
            if number <= 0:
                print("Valeur invalide. Le nombre doit être > 0.")
                continue
            return number
        except ValueError:
            print("Entrée invalide. Exemple: 84000 ou 3350.5")


def safe_str_input(label: str, default: str = "") -> str:
    value = input(f"{label}" + (f" [{default}]" if default else "") + ": ").strip()
    return value if value else default


def ask_asset() -> str:
    allowed = ", ".join(sorted(ALLOWED_ASSETS))
    while True:
        asset = input(f"Asset ({allowed}): ").strip().upper()
        if asset in ALLOWED_ASSETS:
            return asset
        print("Asset invalide.")


def ask_action() -> str:
    while True:
        action = input("Action (BUY/SELL): ").strip().upper()
        if action in ALLOWED_ACTIONS:
            return action
        print("Action invalide.")


def validate_prices(action: str, entry: float, sl: float, tp: float) -> tuple[bool, str | None]:
    if action == "BUY":
        if not (sl < entry < tp):
            return False, "Pour un BUY, il faut: stop_loss < entry_price < take_profit"
    elif action == "SELL":
        if not (tp < entry < sl):
            return False, "Pour un SELL, il faut: take_profit < entry_price < stop_loss"
    else:
        return False, "Action invalide"
    return True, None


def compute_rr(entry: float, sl: float, tp: float) -> float | None:
    try:
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        if risk <= 0:
            return None
        return round(reward / risk, 2)
    except Exception:
        return None


def build_payload() -> dict:
    asset = ask_asset()
    action = ask_action()
    entry_price = safe_float_input("Entry price")
    stop_loss = safe_float_input("Stop loss")
    take_profit = safe_float_input("Take profit")

    is_valid, error = validate_prices(action, entry_price, stop_loss, take_profit)
    if not is_valid:
        print(f"\nErreur validation: {error}")
        sys.exit(1)
def ask_timeframe():
    allowed = {"1m", "5m", "15m", "1h", "4h"}
    while True:
        tf = input("Timeframe (1m,5m,15m,1h,4h) [15m]: ").strip() or "15m"
        if tf in allowed:
            return tf
        print("Timeframe invalide.")

    timeframe =ask_timeframe() 
    trend = safe_str_input("Trend", "bullish" if action == "BUY" else "bearish")
    setup_note = safe_str_input("Setup note", "IA signal")
    confidence_raw = safe_str_input("Confidence (optionnel)", "")

    confidence = None
    if confidence_raw:
        try:
            confidence = float(confidence_raw.replace(",", "."))
        except ValueError:
            print("Confidence invalide, ignorée.")
            confidence = None

    rr = compute_rr(entry_price, stop_loss, take_profit)

    print("\nRésumé signal")
    print("-" * 72)
    print(f"Asset      : {asset}")
    print(f"Action     : {action}")
    print(f"Entry      : {entry_price}")
    print(f"SL         : {stop_loss}")
    print(f"TP         : {take_profit}")
    print(f"Timeframe  : {timeframe}")
    print(f"Trend      : {trend}")
    print(f"RR         : {rr if rr is not None else 'N/A'}")
    print(f"Note       : {setup_note}")
    print("-" * 72)

    confirm = input("Confirmer envoi ? (y/n): ").strip().lower()
    if confirm not in {"y", "yes", "o", "oui"}:
        print("Envoi annulé.")
        sys.exit(0)

    payload = {
        "secret": SECRET,
        "asset": asset,
        "action": action,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "timeframe": timeframe,
        "signal_type": "manual",
        "trend": trend,
        "setup_note": setup_note,
    }

    if confidence is not None:
        payload["confidence"] = confidence

    return payload


def send_signal(payload: dict):
    started_at = datetime.utcnow()

    try:
        response = requests.post(
            API_ENDPOINT,
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
    payload = build_payload()
    send_signal(payload)


if __name__ == "__main__":
    main()