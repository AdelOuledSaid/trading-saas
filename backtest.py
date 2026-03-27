from datetime import datetime, timezone
import requests
import pandas as pd

# =========================
# CONFIG
# =========================
COIN = "BTC"
INTERVAL = "5m"
LOOKBACK_CANDLES = 500

MA_FAST = 9
MA_SLOW = 21
RSI_PERIOD = 14
BREAKOUT_LOOKBACK = 5


# =========================
# DATA HYPERLIQUID
# =========================
def get_historical_data() -> pd.DataFrame:
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

    start_ms = now_ms - (LOOKBACK_CANDLES + 20) * interval_to_ms[INTERVAL]

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
# INDICATORS
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


def prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ma_fast"] = df["close"].rolling(MA_FAST).mean()
    df["ma_slow"] = df["close"].rolling(MA_SLOW).mean()
    df["rsi"] = compute_rsi(df["close"], RSI_PERIOD)
    return df


# =========================
# STRATEGY
# =========================
def generate_signal_at_index(df: pd.DataFrame, i: int):
    if i < max(MA_SLOW, RSI_PERIOD) + BREAKOUT_LOOKBACK + 5:
        return None

    last = df.iloc[i]
    prev = df.iloc[i - 1]
    prev2 = df.iloc[i - 2]

    recent_high = df["high"].iloc[i - BREAKOUT_LOOKBACK:i].max()
    recent_low = df["low"].iloc[i - BREAKOUT_LOOKBACK:i].min()

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
            "action": "BUY",
            "entry_price": round(entry_price, 2),
            "stop_loss": round(stop_loss, 2),
            "take_profit": round(take_profit, 2),
            "entry_index": i
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
            "action": "SELL",
            "entry_price": round(entry_price, 2),
            "stop_loss": round(stop_loss, 2),
            "take_profit": round(take_profit, 2),
            "entry_index": i
        }

    return None


# =========================
# BACKTEST ENGINE
# =========================
def run_backtest(df: pd.DataFrame):
    trades = []
    open_trade = None

    for i in range(len(df)):
        candle = df.iloc[i]

        if open_trade is not None:
            if open_trade["action"] == "BUY":
                if candle["low"] <= open_trade["stop_loss"]:
                    open_trade["status"] = "LOSS"
                    open_trade["exit_price"] = open_trade["stop_loss"]
                    open_trade["exit_index"] = i
                    open_trade["pnl"] = open_trade["exit_price"] - open_trade["entry_price"]
                    trades.append(open_trade)
                    open_trade = None
                    continue

                if candle["high"] >= open_trade["take_profit"]:
                    open_trade["status"] = "WIN"
                    open_trade["exit_price"] = open_trade["take_profit"]
                    open_trade["exit_index"] = i
                    open_trade["pnl"] = open_trade["exit_price"] - open_trade["entry_price"]
                    trades.append(open_trade)
                    open_trade = None
                    continue

            elif open_trade["action"] == "SELL":
                if candle["high"] >= open_trade["stop_loss"]:
                    open_trade["status"] = "LOSS"
                    open_trade["exit_price"] = open_trade["stop_loss"]
                    open_trade["exit_index"] = i
                    open_trade["pnl"] = open_trade["entry_price"] - open_trade["exit_price"]
                    trades.append(open_trade)
                    open_trade = None
                    continue

                if candle["low"] <= open_trade["take_profit"]:
                    open_trade["status"] = "WIN"
                    open_trade["exit_price"] = open_trade["take_profit"]
                    open_trade["exit_index"] = i
                    open_trade["pnl"] = open_trade["entry_price"] - open_trade["exit_price"]
                    trades.append(open_trade)
                    open_trade = None
                    continue

        if open_trade is None:
            signal = generate_signal_at_index(df, i)
            if signal:
                open_trade = signal

    return trades


# =========================
# STATS
# =========================
def print_stats(trades):
    total = len(trades)
    wins = sum(1 for t in trades if t["status"] == "WIN")
    losses = sum(1 for t in trades if t["status"] == "LOSS")
    winrate = (wins / total * 100) if total > 0 else 0
    total_pnl = sum(t["pnl"] for t in trades)

    sum_wins = sum(t["pnl"] for t in trades if t["status"] == "WIN")
    sum_losses = sum(t["pnl"] for t in trades if t["status"] == "LOSS")

    print("\n===== RESULTATS BACKTEST =====")
    print(f"Nombre de trades : {total}")
    print(f"Gagnants         : {wins}")
    print(f"Perdants         : {losses}")
    print(f"Winrate          : {winrate:.2f}%")
    print(f"PnL total        : {total_pnl:.2f}")
    print(f"Somme gains      : {sum_wins:.2f}")
    print(f"Somme pertes     : {sum_losses:.2f}")

    if total > 0:
        print("\nDerniers trades :")
        for t in trades[-5:]:
            print(
                f"{t['action']} | entrée={t['entry_price']:.2f} | "
                f"SL={t['stop_loss']:.2f} | TP={t['take_profit']:.2f} | "
                f"status={t['status']} | pnl={t['pnl']:.2f}"
            )


# =========================
# MAIN
# =========================
if __name__ == "__main__":
    print("Récupération des données Hyperliquid...")
    df = get_historical_data()
    df = prepare_data(df)

    print(f"{len(df)} bougies récupérées.")
    trades = run_backtest(df)
    print_stats(trades)