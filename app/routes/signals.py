import requests
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify
from flask_login import current_user

from app.extensions import db
from app.models import Signal, TradeReplay, UserReplayDecision
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


def _get_user_plan():
    return (
        getattr(current_user, "plan", "free")
        if getattr(current_user, "is_authenticated", False)
        else "free"
    )


@signals_bp.route("/<lang_code>/signals")
def signals_page(lang_code):
    return render_template("signals/index.html")


@signals_bp.route("/<lang_code>/results")
def results(lang_code):
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

    user_plan = _get_user_plan()
    signal_limit = signal_limit_for_plan(user_plan)
    recent_signals = list(reversed(all_signals[-signal_limit:])) if signal_limit > 0 else []

    total_signals = len(all_signals)
    win_signals = sum(1 for s in all_signals if s.status == "WIN")
    loss_signals = sum(1 for s in all_signals if s.status == "LOSS")
    open_signals = sum(1 for s in all_signals if s.status == "OPEN")
    closed_signals = win_signals + loss_signals

    can_view_stats = has_access(user_plan, "advanced_stats")

    featured_query = Signal.query.filter(Signal.status == "WIN")

    if asset_filter != "ALL":
        featured_query = featured_query.filter(Signal.asset == asset_filter)

    if time_threshold is not None:
        featured_query = featured_query.filter(Signal.created_at >= time_threshold)

    featured_with_percent = (
        featured_query
        .filter(
            Signal.result_percent.isnot(None),
            Signal.result_percent > 0
        )
        .order_by(Signal.result_percent.desc())
        .limit(2)
        .all()
    )

    if len(featured_with_percent) >= 2:
        featured_signals = featured_with_percent
    else:
        featured_signals = (
            featured_query
            .order_by(Signal.created_at.desc())
            .limit(2)
            .all()
        )

    if not featured_signals:
        fallback_query = Signal.query

        if asset_filter != "ALL":
            fallback_query = fallback_query.filter(Signal.asset == asset_filter)

        if time_threshold is not None:
            fallback_query = fallback_query.filter(Signal.created_at >= time_threshold)

        featured_signals = (
            fallback_query
            .order_by(Signal.created_at.desc())
            .limit(2)
            .all()
        )

    recent_cutoff = datetime.utcnow() - timedelta(days=7)
    recent_closed = [
        s for s in all_signals
        if s.created_at and s.created_at >= recent_cutoff and s.status in {"WIN", "LOSS"}
    ]

    if recent_closed:
        recent_wins = len([s for s in recent_closed if s.status == "WIN"])
        recent_success_rate = round((recent_wins / len(recent_closed)) * 100, 2)
    else:
        recent_success_rate = None

    if can_view_stats:
        winrate = round((win_signals / closed_signals) * 100, 2) if closed_signals > 0 else 0

        closed_trade_pnls = [
            calculate_trade_pnl(signal)
            for signal in all_signals
            if signal.status in {"WIN", "LOSS"}
        ]
        estimated_pnl = round(sum(closed_trade_pnls), 2)

        positive_pnls = [p for p in closed_trade_pnls if p > 0]
        negative_pnls = [p for p in closed_trade_pnls if p < 0]

        avg_win = round(sum(positive_pnls) / len(positive_pnls), 2) if positive_pnls else 0
        avg_loss = round(sum(negative_pnls) / len(negative_pnls), 2) if negative_pnls else 0

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
        featured_signals=featured_signals,
        recent_success_rate=recent_success_rate,
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


@signals_bp.route("/api/replay/<int:signal_id>")
def api_replay(signal_id):
    signal = Signal.query.get_or_404(signal_id)

    if signal.replay and signal.replay.candles:
        replay = signal.replay

        candles = [
            {
                "time": candle.candle_time.isoformat(),
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "index": candle.position_index,
            }
            for candle in replay.candles
        ]

        events = [
            {
                "index": event.position_index,
                "title": event.title,
                "description": event.description or "",
                "event_type": event.event_type,
                "price_level": event.price_level,
                "time": event.event_time.isoformat() if event.event_time else None,
            }
            for event in replay.events
        ]

        return jsonify({
            "trade": {
                "symbol": replay.symbol,
                "direction": replay.direction,
                "entry_price": replay.entry_price,
                "stop_loss": replay.stop_loss,
                "take_profit": replay.take_profit,
                "result": replay.result or "OPEN",
                "result_percent": replay.result_percent,
                "timeframe": replay.timeframe,
            },
            "candles": candles,
            "events": events,
        })

    entry = float(signal.entry_price or 100.0)
    stop_loss = float(signal.stop_loss or (entry * 0.99))
    take_profit = float(signal.take_profit or (entry * 1.02))
    direction = (signal.action or "BUY").upper()
    result = (signal.status or "OPEN").upper()

    candles = []
    base_time = datetime.utcnow() - timedelta(minutes=60)

    for i in range(60):
        wave = ((i % 8) - 4) * (entry * 0.00035)
        trend = i * entry * 0.00008

        if direction == "SELL":
            trend = -trend

        price = entry + wave + trend

        if result == "WIN" and i > 38:
            if direction == "BUY":
                price += (take_profit - entry) * ((i - 38) / 22)
            else:
                price -= abs(take_profit - entry) * ((i - 38) / 22)
        elif result == "LOSS" and i > 38:
            if direction == "BUY":
                price -= abs(entry - stop_loss) * ((i - 38) / 22)
            else:
                price += abs(entry - stop_loss) * ((i - 38) / 22)

        open_price = round(price - (entry * 0.00045), 2)
        close_price = round(price + (entry * 0.00045), 2)
        high_price = round(max(open_price, close_price) + (entry * 0.0009), 2)
        low_price = round(min(open_price, close_price) - (entry * 0.0009), 2)

        candles.append({
            "time": (base_time + timedelta(minutes=i)).isoformat(),
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "volume": None,
            "index": i,
        })

    events = [
        {
            "index": 3,
            "title": "Observation du setup",
            "description": "Le marché arrive sur une zone intéressante avec contexte technique exploitable.",
            "event_type": "context",
            "price_level": entry,
            "time": (base_time + timedelta(minutes=3)).isoformat(),
        },
        {
            "index": 8,
            "title": "Entrée validée",
            "description": f"Entrée {direction} proche de {entry}. Le plan est activé avec niveaux définis.",
            "event_type": "entry",
            "price_level": entry,
            "time": (base_time + timedelta(minutes=8)).isoformat(),
        },
        {
            "index": 20,
            "title": "Phase de respiration",
            "description": "Le marché consolide avant le mouvement principal. Discipline requise.",
            "event_type": "pullback",
            "price_level": entry,
            "time": (base_time + timedelta(minutes=20)).isoformat(),
        },
        {
            "index": 32,
            "title": "Point de décision",
            "description": "Retour temporaire contre la position. Gestion émotionnelle importante.",
            "event_type": "decision",
            "price_level": entry,
            "time": (base_time + timedelta(minutes=32)).isoformat(),
        },
        {
            "index": 52,
            "title": "Développement final",
            "description": "Le trade entre dans sa phase décisive avec accélération du mouvement.",
            "event_type": "expansion",
            "price_level": take_profit if result == "WIN" else stop_loss,
            "time": (base_time + timedelta(minutes=52)).isoformat(),
        },
    ]

    return jsonify({
        "trade": {
            "symbol": signal.asset or "BTCUSD",
            "direction": direction,
            "entry_price": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "result": result,
            "result_percent": signal.result_percent,
            "timeframe": signal.timeframe or "15m",
        },
        "candles": candles,
        "events": events,
    })


@signals_bp.route("/api/replay/<int:signal_id>/decision", methods=["POST"])
def replay_decision(signal_id):
    signal = Signal.query.get_or_404(signal_id)

    if not signal.replay:
        return jsonify({"error": "Replay introuvable pour ce signal."}), 404

    if not current_user.is_authenticated:
        return jsonify({"error": "Authentification requise."}), 401

    payload = request.get_json(silent=True) or {}

    decision = (payload.get("decision") or "").strip().lower()
    score = int(payload.get("score") or 0)
    status = (payload.get("status") or "").strip().lower() or None
    feedback = (payload.get("feedback") or "").strip() or None

    if decision not in {"close", "hold", "partial"}:
        return jsonify({"error": "Décision invalide."}), 400

    replay = signal.replay

    new_decision = UserReplayDecision(
        user_id=current_user.id,
        trade_replay_id=replay.id,
        decision=decision,
        score=score,
        status=status,
        feedback=feedback,
    )

    db.session.add(new_decision)
    db.session.commit()

    return jsonify({
        "status": "ok",
        "saved": True,
        "decision": decision,
        "score": score,
    })


@signals_bp.route("/<lang_code>/signals/btc")
def signals_btc(lang_code):
    user_plan = _get_user_plan()
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


@signals_bp.route("/<lang_code>/signals/eth")
def eth_signals_page(lang_code):
    user_plan = _get_user_plan()
    signal_limit = signal_limit_for_plan(user_plan)

    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": "ethereum",
            "vs_currencies": "usd",
            "include_market_cap": "true",
            "include_24hr_vol": "true",
            "include_24hr_change": "true",
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


@signals_bp.route("/<lang_code>/signals/gold")
def signals_gold(lang_code):
    user_plan = _get_user_plan()
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


@signals_bp.route("/<lang_code>/signals/us100")
def signals_us100(lang_code):
    user_plan = _get_user_plan()
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