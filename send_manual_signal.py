import json
import sys
from datetime import datetime
import requests
import os
from dotenv import load_dotenv

load_dotenv()

SECRET = os.getenv("MANUAL_SIGNAL_SECRET")

API_BASE_URL = "http://127.0.0.1:5000"
API_ENDPOINT = f"{API_BASE_URL}/api/manual-signal"
DEFAULT_TIMEOUT = 20

ALLOWED_ASSETS = {
    "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD",
    "GOLD", "US100", "US500", "FRA40",
}
ALLOWED_ACTIONS = {"BUY", "SELL"}
ALLOWED_TIMEFRAMES = {"1m", "5m", "15m", "1h", "4h"}


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


def ask_timeframe() -> str:
    while True:
        tf = input("Timeframe (1m,5m,15m,1h,4h) [15m]: ").strip() or "15m"
        if tf in ALLOWED_TIMEFRAMES:
            return tf
        print("Timeframe invalide.")


def validate_prices(action: str, entry: float, sl: float, tp: float):
    if action == "BUY":
        return sl < entry < tp, "Pour un BUY, il faut: stop_loss < entry_price < take_profit"
    if action == "SELL":
        return tp < entry < sl, "Pour un SELL, il faut: take_profit < entry_price < stop_loss"
    return False, "Action invalide"


def compute_rr(entry: float, sl: float, tp: float):
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    if risk <= 0:
        return None
    return round(reward / risk, 2)


def build_payload() -> dict:
    asset = ask_asset()
    action = ask_action()
    entry_price = safe_float_input("Entry price")
    stop_loss = safe_float_input("Stop loss")
    take_profit = safe_float_input("Take profit")
    timeframe = ask_timeframe()
    trend = safe_str_input("Trend", "bullish" if action == "BUY" else "bearish")
    setup_note = safe_str_input("Setup note", "IA signal")
    confidence_raw = safe_str_input("Confidence (optionnel)", "")

    is_valid, error = validate_prices(action, entry_price, stop_loss, take_profit)
    if not is_valid:
        print(f"\nErreur validation: {error}")
        sys.exit(1)

    confidence = None
    if confidence_raw:
        try:
            confidence = float(confidence_raw.replace(",", "."))
        except ValueError:
            print("Confidence invalide, ignorée.")

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
    print(f"Secret     : {repr(SECRET)}")
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
        "signal_type": "auto",
        "trend": trend,
        "setup_note": setup_note,
    }

    if confidence is not None:
        payload["confidence"] = confidence

    return payload


def send_signal(payload: dict):
    started_at = datetime.utcnow()

    try:
        response = requests.post(API_ENDPOINT, json=payload, timeout=DEFAULT_TIMEOUT)
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