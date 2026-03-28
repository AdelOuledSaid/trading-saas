import time
import sqlite3
from datetime import datetime, timezone
import requests
import pandas as pd

# =========================
# CONFIG
# =========================
TELEGRAM_BOT_TOKEN = "..............."
TELEGRAM_CHAT_ID = "...................."

COIN = "BTC"
INTERVAL = "5m"
LOOKBACK_CANDLES = 120
CHECK_INTERVAL = 300
DB_PATH = "instance/users.db"

MA_FAST = 9
MA_SLOW = 21
RSI_PERIOD = 14
BREAKOUT_LOOKBACK = 5


# =========================
# TELEGRAM
# =========================
def send_telegram_message(message: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        print("TELEGRAM:", response.status_code, response.text)
    except Exception as e:
        print("Erreur Telegram :", e)


# =========================
# DB
# =========================
def save_signal(asset: str, action: str, entry_price: float, stop_loss: float, take_profit: float) -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO signal (asset, action, entry_price, stop_loss, take_profit, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        asset,
        action,
        entry_price,
        stop_loss,
        take_profit,
        "OPEN",
        datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()


def get_last_signal() -> tuple | None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT asset, action, entry_price
        FROM signal
        ORDER BY id DESC
        LIMIT 1
    """)
    row = cursor.fetchone()

    conn.close()
    return row


def is_duplicate_signal(signal: dict) -> bool:
    last_signal = get_last_signal()
    if not last_signal:
        return False

    asset, action, entry_price = last_signal
    return (
        asset == signal["asset"]
        and action == signal["action"]
        and abs(float(entry_price) - float(signal["entry_price"])) < 1e-9
    )


def has_recent_signal(asset: str, minutes: int = 30) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT created_at
        FROM signal
        WHERE asset = ?
        ORDER BY id DESC
        LIMIT 1
    """, (asset,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return False

    last_time = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
    diff = datetime.utcnow() - last_time

    return diff.total_seconds() < minutes * 60


def update_open_signals_with_current_price(current_price: float) -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, action, stop_loss, take_profit
        FROM signal
        WHERE status = 'OPEN'
    """)
    open_signals = cursor.fetchall()

    for signal_id, action, stop_loss, take_profit in open_signals:
        new_status = None

        if action == "BUY":
            if current_price >= take_profit:
                new_status = "WIN"
            elif current_price <= stop_loss:
                new_status = "LOSS"

        elif action == "SELL":
            if current_price <= take_profit:
                new_status = "WIN"
            elif current_price >= stop_loss:
                new_status = "LOSS"

        if new_status:
            cursor.execute("""
                UPDATE signal
                SET status = ?
                WHERE id = ?
            """, (new_status, signal_id))
            print(f"Signal {signal_id} clôturé en {new_status}")

    conn.commit()
    conn.close()


# =========================
# DATA HYPERLIQUID
# =========================
def get_real_data() -> pd.DataFrame:
    url = "https://api.hyperliquid.xyz/info"

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    interval_to_ms = {
        "1m": 60_000,
        "3m": 180_000,
        "5m": 300_000,
        "15m": 900_000,
        "30m": 1_800_000,
        "1h": 3_600_000,
        "2h": 7_200_000,
        "4h": 14_400_000,
        "8h": 28_800_000,
        "12h": 43_200_000,
        "1d": 86_400_000,
    }

    if INTERVAL not in interval_to_ms:
        raise ValueError(f"Intervalle non géré: {INTERVAL}")

    start_ms = now_ms - (LOOKBACK_CANDLES + 10) * interval_to_ms[INTERVAL]

    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin": COIN,
            "interval": INTERVAL,
            "startTime": start_ms,
            "endTime": now_ms
        }
    }

    response = requests.post(url, json=payload, timeout=15)
    response.raise_for_status()
    data = response.json()

    if not isinstance(data, list) or len(data) == 0:
        raise ValueError(f"Réponse Hyperliquid vide ou inattendue: {data}")

    rows = []
    for candle in data:
        rows.append({
            "time": candle.get("t"),
            "open": float(candle.get("o")),
            "high": float(candle.get("h")),
            "low": float(candle.get("l")),
            "close": float(candle.get("c")),
            "volume": float(candle.get("v")),
        })

    df = pd.DataFrame(rows).sort_values("time").reset_index(drop=True)

    if len(df) > LOOKBACK_CANDLES:
        df = df.tail(LOOKBACK_CANDLES).reset_index(drop=True)

    return df


# =========================
# STRATEGY
# =========================
def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()

    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)

    avg_gain = gains.rolling(window=period).mean()
    avg_loss = losses.rolling(window=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


def generate_signal(df: pd.DataFrame) -> dict | None:
    min_needed = max(MA_SLOW, RSI_PERIOD) + BREAKOUT_LOOKBACK + 5
    if len(df) < min_needed:
        print(f"Pas assez de données: {len(df)} bougies")
        return None

    df = df.copy()
    df["ma_fast"] = df["close"].rolling(MA_FAST).mean()
    df["ma_slow"] = df["close"].rolling(MA_SLOW).mean()
    df["rsi"] = compute_rsi(df["close"], RSI_PERIOD)

    last = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]

    recent_high = df["high"].iloc[-BREAKOUT_LOOKBACK:].max()
    recent_low = df["low"].iloc[-BREAKOUT_LOOKBACK:].min()

    ma_slow_rising = (
        pd.notna(last["ma_slow"])
        and pd.notna(prev["ma_slow"])
        and pd.notna(prev2["ma_slow"])
        and last["ma_slow"] > prev["ma_slow"] > prev2["ma_slow"]
    )

    ma_slow_falling = (
        pd.notna(last["ma_slow"])
        and pd.notna(prev["ma_slow"])
        and pd.notna(prev2["ma_slow"])
        and last["ma_slow"] < prev["ma_slow"] < prev2["ma_slow"]
    )

    ma_gap_ok = (
        pd.notna(last["ma_fast"])
        and pd.notna(last["ma_slow"])
        and abs(last["ma_fast"] - last["ma_slow"]) > 30
    )

    candle_size_ok = (last["high"] - last["low"]) < 400

    # BUY
    if (
        pd.notna(last["ma_fast"])
        and pd.notna(last["ma_slow"])
        and pd.notna(last["rsi"])
        and last["ma_fast"] > last["ma_slow"]
        and ma_gap_ok
        and last["rsi"] > 55
        and last["close"] > recent_high
        and (last["close"] - recent_high) < 150
        and candle_size_ok
        and ma_slow_rising
    ):
        entry_price = float(last["close"])
        risk = min(300, max(120, (last["high"] - last["low"]) * 2))
        stop_loss = entry_price - risk
        take_profit = entry_price + (risk * 1.5)

        return {
            "asset": COIN,
            "action": "BUY",
            "entry_price": round(entry_price, 2),
            "stop_loss": round(stop_loss, 2),
            "take_profit": round(take_profit, 2)
        }

    # SELL
    if (
        pd.notna(last["ma_fast"])
        and pd.notna(last["ma_slow"])
        and pd.notna(last["rsi"])
        and last["ma_fast"] < last["ma_slow"]
        and ma_gap_ok
        and last["rsi"] < 45
        and last["close"] < recent_low
        and (recent_low - last["close"]) < 150
        and candle_size_ok
        and ma_slow_falling
    ):
        entry_price = float(last["close"])
        risk = min(300, max(120, (last["high"] - last["low"]) * 2))
        stop_loss = entry_price + risk
        take_profit = entry_price - (risk * 1.5)

        return {
            "asset": COIN,
            "action": "SELL",
            "entry_price": round(entry_price, 2),
            "stop_loss": round(stop_loss, 2),
            "take_profit": round(take_profit, 2)
        }

    return None


# =========================
# MAIN LOOP
# =========================
def run_bot() -> None:
    print("Bot Hyperliquid final démarré...")

    while True:
        try:
            df = get_real_data()
            current_price = float(df.iloc[-1]["close"])

            update_open_signals_with_current_price(current_price)

            print(f"{len(df)} bougies récupérées | dernier close = {current_price}")

            signal = generate_signal(df)

            if signal:
                if not is_duplicate_signal(signal):
                    if has_recent_signal(signal["asset"], minutes=30):
                        print("Signal récent détecté, cooldown actif.")
                    else:
                        save_signal(
                            asset=signal["asset"],
                            action=signal["action"],
                            entry_price=signal["entry_price"],
                            stop_loss=signal["stop_loss"],
                            take_profit=signal["take_profit"]
                        )

                        message = (
                            f"🚨 Signal bot Hyperliquid\n"
                            f"Actif: {signal['asset']}\n"
                            f"Action: {signal['action']}\n"
                            f"Prix: {signal['entry_price']}\n"
                            f"SL: {signal['stop_loss']}\n"
                            f"TP: {signal['take_profit']}\n"
                            f"Status: OPEN"
                        )
                        send_telegram_message(message)
                        print("Signal envoyé :", signal)
                else:
                    print("Signal dupliqué, ignoré.")
            else:
                print("Aucun signal.")

        except Exception as e:
            print("Erreur bot :", e)

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    run_bot()