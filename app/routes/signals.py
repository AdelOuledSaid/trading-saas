import requests
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request
from flask_login import current_user

from app.models import Signal
from app.services.signal_service import calculate_trade_pnl
from app.services.market_service import (
    get_crypto_market_live,
    format_big_number,
    get_asset_news,
    get_fear_greed_live,
    get_btc_dominance_live,
)
from app.access import signal_limit_for_plan, has_access

signals_bp = Blueprint("signals", __name__)


@signals_bp.route("/signals")
def signals_page():
    return render_template("signals/index.html")


@signals_bp.route("/results")
def results():
    asset_filter = request.args.get("asset", "ALL").upper().strip()
    time_filter = request.args.get("time", "all").lower().strip()

    allowed_assets = {"ALL", "BTCUSD", "ETHUSD", "GOLD", "US100"}
    allowed_times = {"all", "15m", "1h", "1d", "1w", "1m"}

    if asset_filter not in allowed_assets:
        asset_filter = "ALL"

    if time_filter not in allowed_times:
        time_filter = "all"

    query = Signal.query

    if asset_filter != "ALL":
        query = query.filter(Signal.asset == asset_filter)

    now = datetime.utcnow()
    time_threshold = None

    if time_filter == "15m":
        time_threshold = now - timedelta(minutes=15)
    elif time_filter == "1h":
        time_threshold = now - timedelta(hours=1)
    elif time_filter == "1d":
        time_threshold = now - timedelta(days=1)
    elif time_filter == "1w":
        time_threshold = now - timedelta(weeks=1)
    elif time_filter == "1m":
        time_threshold = now - timedelta(days=30)

    if time_threshold is not None:
        query = query.filter(Signal.created_at >= time_threshold)

    all_signals = query.order_by(Signal.created_at.asc()).all()

    user_plan = getattr(current_user, "plan", "free") if getattr(current_user, "is_authenticated", False) else "free"
    signal_limit = signal_limit_for_plan(user_plan)

    recent_signals = list(reversed(all_signals[-signal_limit:])) if signal_limit > 0 else []

    total_signals = len(all_signals)
    win_signals = sum(1 for s in all_signals if s.status == "WIN")
    loss_signals = sum(1 for s in all_signals if s.status == "LOSS")
    open_signals = sum(1 for s in all_signals if s.status == "OPEN")
    closed_signals = win_signals + loss_signals

    can_view_stats = has_access(user_plan, "advanced_stats")

    if can_view_stats:
        winrate = round((win_signals / closed_signals) * 100, 2) if closed_signals > 0 else 0

        closed_trade_pnls = [
            calculate_trade_pnl(signal)
            for signal in all_signals
            if signal.status in {"WIN", "LOSS"}
        ]
        estimated_pnl = round(sum(closed_trade_pnls), 2)

        avg_win = round(
            sum(p for p in closed_trade_pnls if p > 0) / len([p for p in closed_trade_pnls if p > 0]),
            2
        ) if any(p > 0 for p in closed_trade_pnls) else 0

        avg_loss = round(
            sum(p for p in closed_trade_pnls if p < 0) / len([p for p in closed_trade_pnls if p < 0]),
            2
        ) if any(p < 0 for p in closed_trade_pnls) else 0

        rr_values = []
        for signal in all_signals:
            rr = None
            try:
                rr = signal.risk_reward or signal.compute_rr()
            except Exception:
                rr = signal.risk_reward

            if rr not in [None, "", "—"]:
                try:
                    rr_values.append(float(rr))
                except Exception:
                    pass

        avg_rr = round(sum(rr_values) / len(rr_values), 2) if rr_values else 0

        asset_stats = {}
        for signal in all_signals:
            asset = signal.asset or "UNKNOWN"
            asset_stats.setdefault(asset, {"count": 0, "pnl": 0.0})
            asset_stats[asset]["count"] += 1
            if signal.status in {"WIN", "LOSS"}:
                asset_stats[asset]["pnl"] += calculate_trade_pnl(signal)

        best_asset = "—"
        best_asset_pnl = 0
        if asset_stats:
            best_asset, best_data = max(asset_stats.items(), key=lambda item: item[1]["pnl"])
            best_asset_pnl = round(best_data["pnl"], 2)

        equity_curve = []
        running_pnl = 0.0
        for signal in all_signals:
            if signal.status in {"WIN", "LOSS"}:
                running_pnl += calculate_trade_pnl(signal)
                equity_curve.append(round(running_pnl, 2))

        if not equity_curve:
            equity_curve = [0]
    else:
        winrate = None
        estimated_pnl = None
        avg_rr = None
        avg_win = None
        avg_loss = None
        best_asset = None
        best_asset_pnl = None
        equity_curve = []

    return render_template(
        "results.html",
        signals=recent_signals,
        total_signals=total_signals,
        win_signals=win_signals,
        loss_signals=loss_signals,
        open_signals=open_signals,
        closed_signals=closed_signals,
        winrate=winrate,
        estimated_pnl=estimated_pnl,
        avg_rr=avg_rr,
        avg_win=avg_win,
        avg_loss=avg_loss,
        best_asset=best_asset,
        best_asset_pnl=best_asset_pnl,
        selected_asset=asset_filter,
        selected_time=time_filter,
        available_assets=["ALL", "BTCUSD", "ETHUSD", "GOLD", "US100"],
        available_times=[
            ("all", "Tout"),
            ("15m", "15 min"),
            ("1h", "1 heure"),
            ("1d", "1 jour"),
            ("1w", "1 semaine"),
            ("1m", "1 mois"),
        ],
        equity_curve=equity_curve,
        user_plan=user_plan,
        signal_limit=signal_limit,
        can_view_stats=can_view_stats,
    )


@signals_bp.route("/signals/btc")
def signals_btc():
    user_plan = getattr(current_user, "plan", "free") if getattr(current_user, "is_authenticated", False) else "free"
    signal_limit = signal_limit_for_plan(user_plan)

    btc_signals = (
        Signal.query
        .filter_by(asset="BTCUSD")
        .order_by(Signal.created_at.desc())
        .limit(signal_limit if signal_limit > 0 else 0)
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
        fear_greed=get_fear_greed_live(),
        user_plan=user_plan,
        signal_limit=signal_limit,
    )


@signals_bp.route("/signals/eth")
def eth_signals_page():
    user_plan = getattr(current_user, "plan", "free") if getattr(current_user, "is_authenticated", False) else "free"
    signal_limit = signal_limit_for_plan(user_plan)

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

    eth_signals = (
        Signal.query
        .filter_by(asset="ETHUSD")
        .order_by(Signal.created_at.desc())
        .limit(signal_limit if signal_limit > 0 else 0)
        .all()
    )

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
        eth_estimated_pnl=eth_estimated_pnl,
        user_plan=user_plan,
        signal_limit=signal_limit,
    )


@signals_bp.route("/signals/gold")
def signals_gold():
    user_plan = getattr(current_user, "plan", "free") if getattr(current_user, "is_authenticated", False) else "free"
    signal_limit = signal_limit_for_plan(user_plan)

    gold_signals = (
        Signal.query
        .filter_by(asset="GOLD")
        .order_by(Signal.created_at.desc())
        .limit(signal_limit if signal_limit > 0 else 0)
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
        gold_estimated_pnl=gold_estimated_pnl,
        user_plan=user_plan,
        signal_limit=signal_limit,
    )


@signals_bp.route("/signals/us100")
def signals_us100():
    user_plan = getattr(current_user, "plan", "free") if getattr(current_user, "is_authenticated", False) else "free"
    signal_limit = signal_limit_for_plan(user_plan)

    us100_signals = (
        Signal.query
        .filter_by(asset="US100")
        .order_by(Signal.created_at.desc())
        .limit(signal_limit if signal_limit > 0 else 0)
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
        us100_estimated_pnl=us100_estimated_pnl,
        user_plan=user_plan,
        signal_limit=signal_limit,
    )