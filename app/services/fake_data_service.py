import random
from datetime import timedelta
from app.models import Signal


def get_fake_asset_base_price(asset: str) -> float:
    prices = {
        "BTCUSD": 68000,
        "ETHUSD": 3200,
        "SOLUSD": 140,
        "XRPUSD": 0.62,
        "GOLD": 3050,
        "US100": 18200,
        "US500": 5400,
        "FRA40": 8100,
    }
    return prices.get(asset.upper(), 1000)


def generate_fake_signal(asset: str, created_at, idx: int) -> Signal:
    asset = asset.upper()
    action = random.choice(["BUY", "SELL"])

    base_price = get_fake_asset_base_price(asset)

    if asset == "BTCUSD":
        entry_price = round(base_price + random.uniform(-2500, 2500), 2)
        sl_distance = random.uniform(120, 260)
        tp_distance = random.uniform(180, 420)
    elif asset == "ETHUSD":
        entry_price = round(base_price + random.uniform(-180, 180), 2)
        sl_distance = random.uniform(20, 60)
        tp_distance = random.uniform(30, 90)
    elif asset == "SOLUSD":
        entry_price = round(base_price + random.uniform(-12, 12), 2)
        sl_distance = random.uniform(3, 8)
        tp_distance = random.uniform(5, 14)
    elif asset == "XRPUSD":
        entry_price = round(base_price + random.uniform(-0.08, 0.08), 4)
        sl_distance = random.uniform(0.01, 0.025)
        tp_distance = random.uniform(0.015, 0.04)
    elif asset == "GOLD":
        entry_price = round(base_price + random.uniform(-35, 35), 2)
        sl_distance = random.uniform(4, 10)
        tp_distance = random.uniform(7, 18)
    elif asset == "US100":
        entry_price = round(base_price + random.uniform(-350, 350), 2)
        sl_distance = random.uniform(45, 110)
        tp_distance = random.uniform(70, 190)
    elif asset == "US500":
        entry_price = round(base_price + random.uniform(-90, 90), 2)
        sl_distance = random.uniform(12, 26)
        tp_distance = random.uniform(18, 42)
    elif asset == "FRA40":
        entry_price = round(base_price + random.uniform(-180, 180), 2)
        sl_distance = random.uniform(22, 50)
        tp_distance = random.uniform(35, 85)
    else:
        entry_price = round(base_price + random.uniform(-100, 100), 2)
        sl_distance = random.uniform(10, 20)
        tp_distance = random.uniform(15, 30)

    decimals = 4 if asset == "XRPUSD" else 2

    if action == "BUY":
        stop_loss = round(entry_price - sl_distance, decimals)
        take_profit = round(entry_price + tp_distance, decimals)
    else:
        stop_loss = round(entry_price + sl_distance, decimals)
        take_profit = round(entry_price - tp_distance, decimals)

    r = random.random()
    if r < 0.68:
        status = "WIN"
        closed_at = created_at + timedelta(hours=random.randint(1, 18), minutes=random.randint(5, 55))
    elif r < 0.90:
        status = "LOSS"
        closed_at = created_at + timedelta(hours=random.randint(1, 18), minutes=random.randint(5, 55))
    else:
        status = "OPEN"
        closed_at = None

    return Signal(
        trade_id=f"FAKE_{asset}_{created_at.strftime('%Y%m%d%H%M%S')}_{idx}",
        asset=asset,
        action=action,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        status=status,
        created_at=created_at,
        closed_at=closed_at
    )