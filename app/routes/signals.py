import requests
from flask import Blueprint, render_template, request

from app.models import Signal
from app.services.signal_service import calculate_trade_pnl
from app.services.market_service import (
    get_crypto_market_live,
    format_big_number,
    get_asset_news,
    get_fear_greed_live,
    get_btc_dominance_live,
)

signals_bp = Blueprint("signals", __name__)


@signals_bp.route("/signals")
def signals_page():
    return render_template("signals/index.html")


@signals_bp.route("/results")
def results():
    all_signals = Signal.query.order_by(Signal.created_at.desc()).limit(50).all()

    total = len(all_signals)
    wins = len([s for s in all_signals if s.status == "WIN"])
    losses = len([s for s in all_signals if s.status == "LOSS"])

    winrate = round((wins / (wins + losses)) * 100, 2) if (wins + losses) > 0 else 0
    pnl = round(sum(calculate_trade_pnl(s) for s in all_signals), 2)

    return render_template(
        "results.html",
        total_signals=total,
        total_win=wins,
        total_loss=losses,
        winrate=winrate,
        estimated_pnl=pnl,
        signals=all_signals[:10]
    )


@signals_bp.route("/signals/btc")
def signals_btc():
    btc_signals = (
        Signal.query
        .filter_by(asset="BTCUSD")
        .order_by(Signal.created_at.desc())
        .limit(20)
        .all()
    )

    crypto = get_crypto_market_live()
    btc = crypto.get("bitcoin", {})

    btc_price = format_big_number(btc.get("usd")) if btc.get("usd") else "..."
    if btc.get("usd"):
        btc_price = f"{btc.get('usd'):,.2f}".replace(",", " ")
    btc_change = round(btc.get("usd_24h_change", 0), 2) if btc.get("usd_24h_change") else "..."
    btc_market_cap = format_big_number(btc.get("usd_market_cap"))
    btc_volume = format_big_number(btc.get("usd_24h_vol"))

    return render_template(
        "signals/btc.html",
        btc_signals=btc_signals,
        btc_price=btc_price,
        btc_change_24h=btc_change,
        btc_market_cap=btc_market_cap,
        btc_volume_24h=btc_volume,
        btc_news=get_asset_news("BTC"),
        btc_dominance=get_btc_dominance_live(),
        fear_greed=get_fear_greed_live()
    )


@signals_bp.route("/signals/eth")
def eth_signals_page():
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": "ethereum",
            "vs_currencies": "usd",
            "include_market_cap": "true",
            "include_24hr_vol": "true",
            "include_24hr_change": "true"
        }

        res = requests.get(url, params=params, timeout=10)
        data = res.json().get("ethereum", {})

        eth_price = round(data.get("usd", 0), 2)
        eth_change_24h = round(data.get("usd_24h_change", 0), 2)
        eth_volume_24h = round(data.get("usd_24h_vol", 0) / 1e9, 2)
        eth_market_cap = round(data.get("usd_market_cap", 0) / 1e9, 2)

    except Exception:
        eth_price = eth_change_24h = eth_volume_24h = eth_market_cap = None

    try:
        url = "https://api.coingecko.com/api/v3/coins/ethereum"
        res = requests.get(url, timeout=10)
        market = res.json().get("market_data", {})

        eth_high_24h = round(market["high_24h"]["usd"], 2)
        eth_low_24h = round(market["low_24h"]["usd"], 2)

    except Exception:
        eth_high_24h = eth_low_24h = None

    if eth_change_24h:
        if eth_change_24h > 2:
            eth_trend_label = "Haussier 📈"
        elif eth_change_24h < -2:
            eth_trend_label = "Baissier 📉"
        else:
            eth_trend_label = "Neutre"
    else:
        eth_trend_label = "Neutre"

    if eth_change_24h:
        if abs(eth_change_24h) > 4:
            eth_volatility_label = "Élevée ⚡"
        elif abs(eth_change_24h) > 2:
            eth_volatility_label = "Modérée"
        else:
            eth_volatility_label = "Faible"
    else:
        eth_volatility_label = "Modérée"

    try:
        eth_support_1 = round(eth_price * 0.97, 2)
        eth_support_2 = round(eth_price * 0.94, 2)

        eth_resistance_1 = round(eth_price * 1.03, 2)
        eth_resistance_2 = round(eth_price * 1.06, 2)
    except Exception:
        eth_support_1 = eth_support_2 = eth_resistance_1 = eth_resistance_2 = None

    try:
        fg = requests.get("https://api.alternative.me/fng/", timeout=10).json()
        fg_data = fg["data"][0]

        fear_greed_value = fg_data["value"]
        fear_greed_classification = fg_data["value_classification"]

    except Exception:
        fear_greed_value = None
        fear_greed_classification = None

    eth_news = get_asset_news("ETH")

    eth_signals = Signal.query.filter_by(asset="ETHUSD").order_by(Signal.created_at.desc()).limit(10).all()

    total = len(eth_signals)
    wins = len([s for s in eth_signals if s.status == "WIN"])

    eth_total_signals = total
    eth_open_signals = len([s for s in eth_signals if s.status == "OPEN"])

    eth_winrate = round((wins / total) * 100, 2) if total > 0 else 0
    eth_estimated_pnl = wins * 2 - (total - wins)

    return render_template(
        "signals/eth.html",
        eth_price=eth_price,
        eth_change_24h=eth_change_24h,
        eth_volume_24h=eth_volume_24h,
        eth_market_cap=eth_market_cap,
        eth_high_24h=eth_high_24h,
        eth_low_24h=eth_low_24h,
        eth_trend_label=eth_trend_label,
        eth_volatility_label=eth_volatility_label,
        eth_support_1=eth_support_1,
        eth_support_2=eth_support_2,
        eth_resistance_1=eth_resistance_1,
        eth_resistance_2=eth_resistance_2,
        fear_greed_value=fear_greed_value,
        fear_greed_classification=fear_greed_classification,
        eth_news=eth_news,
        eth_signals=eth_signals,
        eth_total_signals=eth_total_signals,
        eth_open_signals=eth_open_signals,
        eth_winrate=eth_winrate,
        eth_estimated_pnl=eth_estimated_pnl
    )


@signals_bp.route("/signals/gold")
def signals_gold():
    gold_signals = (
        Signal.query
        .filter_by(asset="GOLD")
        .order_by(Signal.created_at.desc())
        .limit(20)
        .all()
    )

    gold_total_signals = Signal.query.filter_by(asset="GOLD").count()
    gold_open_signals = Signal.query.filter_by(asset="GOLD", status="OPEN").count()
    gold_win_signals = Signal.query.filter_by(asset="GOLD", status="WIN").count()
    gold_loss_signals = Signal.query.filter_by(asset="GOLD", status="LOSS").count()

    closed_count = gold_win_signals + gold_loss_signals
    gold_winrate = round((gold_win_signals / closed_count) * 100, 2) if closed_count > 0 else 0

    all_gold_signals = Signal.query.filter_by(asset="GOLD").all()
    gold_estimated_pnl = round(sum(calculate_trade_pnl(s) for s in all_gold_signals), 2)

    return render_template(
        "signals/gold.html",
        gold_signals=gold_signals,
        gold_total_signals=gold_total_signals,
        gold_open_signals=gold_open_signals,
        gold_winrate=gold_winrate,
        gold_estimated_pnl=gold_estimated_pnl
    )


@signals_bp.route("/signals/us100")
def signals_us100():
    us100_signals = (
        Signal.query
        .filter_by(asset="US100")
        .order_by(Signal.created_at.desc())
        .limit(20)
        .all()
    )

    us100_total_signals = Signal.query.filter_by(asset="US100").count()
    us100_open_signals = Signal.query.filter_by(asset="US100", status="OPEN").count()
    us100_win_signals = Signal.query.filter_by(asset="US100", status="WIN").count()
    us100_loss_signals = Signal.query.filter_by(asset="US100", status="LOSS").count()

    closed_count = us100_win_signals + us100_loss_signals
    us100_winrate = round((us100_win_signals / closed_count) * 100, 2) if closed_count > 0 else 0

    all_us100_signals = Signal.query.filter_by(asset="US100").all()
    us100_estimated_pnl = round(sum(calculate_trade_pnl(s) for s in all_us100_signals), 2)

    return render_template(
        "signals/us100.html",
        us100_signals=us100_signals,
        us100_total_signals=us100_total_signals,
        us100_open_signals=us100_open_signals,
        us100_winrate=us100_winrate,
        us100_estimated_pnl=us100_estimated_pnl
    )