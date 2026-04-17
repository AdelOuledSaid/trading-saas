from datetime import datetime
from collections import defaultdict
from flask import Blueprint, render_template, request
from flask_login import login_required, current_user

import config
from app.extensions import db
from app.models import Signal
from app.models.replay import TradeReplay
from app.core.decorators import plan_required
from app.services.signal_service import calculate_trade_pnl
from app.services.stripe_service import sync_user_premium_status
from app.services.briefing_service import ensure_daily_briefing
from app.access import signal_limit_for_plan, has_access
from app.services.telegram_dedup import count_sent_today
from app.services.market_service import get_crypto_command_center

dashboard_bp = Blueprint("dashboard", __name__)


TV_SYMBOL_MAP = {
    "BTC": "BINANCE:BTCUSDT",
    "BTCUSD": "BINANCE:BTCUSDT",
    "ETH": "BINANCE:ETHUSDT",
    "ETHUSD": "BINANCE:ETHUSDT",
    "SOL": "BINANCE:SOLUSDT",
    "SOLUSD": "BINANCE:SOLUSDT",
    "XRP": "BINANCE:XRPUSDT",
    "XRPUSD": "BINANCE:XRPUSDT",
    "BNB": "BINANCE:BNBUSDT",
    "BNBUSD": "BINANCE:BNBUSDT",
    "GOLD": "OANDA:XAUUSD",
    "XAUUSD": "OANDA:XAUUSD",
    "EURUSD": "FX:EURUSD",
    "GBPUSD": "FX:GBPUSD",
    "USDJPY": "FX:USDJPY",
    "US100": "FOREXCOM:NSXUSD",
    "NAS100": "FOREXCOM:NSXUSD",
    "SPX": "FOREXCOM:SPXUSD",
    "DAX": "FOREXCOM:GER40",
    "SILVER": "OANDA:XAGUSD",
    "XAGUSD": "OANDA:XAGUSD",
    "OIL": "TVC:USOIL",
}


def resolve_tv_symbol(asset: str) -> str:
    asset = (asset or "").upper().strip()
    return TV_SYMBOL_MAP.get(asset, "BINANCE:BTCUSDT")


def build_asset_leaderboard(all_signals):
    board = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0, "trades": 0})

    for s in all_signals:
        asset = (s.asset or "UNKNOWN").upper()

        if s.status not in ["WIN", "LOSS"]:
            continue

        board[asset]["trades"] += 1
        pnl = calculate_trade_pnl(s)
        board[asset]["pnl"] += pnl

        if s.status == "WIN":
            board[asset]["wins"] += 1
        elif s.status == "LOSS":
            board[asset]["losses"] += 1

    rows = []
    for asset, data in board.items():
        closed = data["wins"] + data["losses"]
        winrate = round((data["wins"] / closed) * 100, 2) if closed else 0
        score = round(data["pnl"] + (data["wins"] * 8) - (data["losses"] * 3), 2)

        rows.append({
            "asset": asset,
            "wins": data["wins"],
            "losses": data["losses"],
            "trades": data["trades"],
            "winrate": winrate,
            "pnl": round(data["pnl"], 2),
            "score": score,
        })

    rows.sort(key=lambda x: (x["score"], x["winrate"], x["wins"]), reverse=True)
    return rows[:4]


def compute_market_energy_label(total_volume_text: str) -> str:
    text = (total_volume_text or "").upper()

    if text.endswith("T"):
        return "EXPLOSIVE"

    if text.endswith("B"):
        try:
            value = float(text[:-1])
        except Exception:
            value = 0

        if value >= 120:
            return "EXPLOSIVE"
        if value >= 50:
            return "ACTIVE"

    return "BUILDING"


def compute_momentum_phase(regime: str) -> str:
    regime = (regime or "").lower()

    if regime == "expansion":
        return "BREAKOUT"
    if regime == "rotation":
        return "ROTATION"
    if regime == "compression":
        return "COMPRESSION"

    return "REVERSAL"


def _build_dashboard_brief_preview(briefing, user_plan: str):
    """
    Retourne:
    - latest_briefing_preview
    - briefing_plan_label
    - can_view_briefing
    """
    if not briefing:
        return None, None, False

    plan = (user_plan or "free").lower()
    content = (getattr(briefing, "content", "") or "").strip()

    if not content:
        return None, None, False

    if plan == "vip":
        vip_content = (
            content
            + "\n\n━━━━━━━━━━━━━━━━━━"
            + "\n🔒 VIP Focus"
            + "\n- zones de liquidité prioritaires"
            + "\n- actifs à surveiller en priorité"
            + "\n- lecture macro / momentum"
            + "\n- scénarios continuation / invalidation"
        )
        preview = type("BriefingPreview", (), {"content": vip_content})()
        return preview, "VIP détaillé", True

    if plan == "premium":
        premium_content = (
            content
            + "\n\n━━━━━━━━━━━━━━━━━━"
            + "\n📊 Premium Focus"
            + "\n- lecture détaillée de la tendance"
            + "\n- zones actives à surveiller"
            + "\n- contexte marché plus complet"
        )
        preview = type("BriefingPreview", (), {"content": premium_content})()
        return preview, "Premium complet", True

    if plan == "basic":
        basic_content = (
            content[:900].strip()
            + "\n\n━━━━━━━━━━━━━━━━━━"
            + "\n📌 Basic Focus"
            + "\n- lecture simple du marché"
            + "\n- zones principales à surveiller"
            + "\n- prudence avant toute entrée"
        )
        preview = type("BriefingPreview", (), {"content": basic_content})()
        return preview, "Basic simplifié", True

    return None, None, False


@dashboard_bp.route("/<lang_code>/dashboard")
@login_required
def dashboard(lang_code):
    sync_user_premium_status(current_user)

    user_plan = getattr(current_user, "plan", "free")

    selected_asset = request.args.get("asset", "").strip().upper()
    if selected_asset and selected_asset not in config.ALLOWED_ASSETS:
        selected_asset = ""

    try:
        market_snapshot = get_crypto_command_center()
    except Exception:
        market_snapshot = {
            "btc_price": "...",
            "eth_price": "...",
            "btc_change_24h": 0,
            "eth_change_24h": 0,
            "btc_dominance": 0,
            "total_market_cap": "...",
            "total_volume": "...",
            "fear_greed_value": 50,
            "fear_greed_label": "Neutral",
            "risk_mode": "Neutral",
            "market_regime": "Compression",
            "dominance_label": "Balanced",
            "altcoin_appetite": "Selective",
            "macro_pressure": "Monitored",
            "execution_mode": "Patience",
            "main_scenario": "Lecture du marché en chargement",
            "invalidation": "Chargement",
            "assets_focus": "BTC / ETH / TOTAL / BTC.D",
            "desk_mode": "Context-Driven",
            "bias_principal": "Chargement",
            "rotation_text": "Chargement",
            "desk_priority": "Context First",
            "momentum_label": "Stable",
            "dominance_state": "Balanced",
            "macro_state": "Monitored",
            "execution_state": "Selective",
            "watchlist": [],
            "ai_confidence": 50,
            "ai_confidence_explanation": "Contexte en chargement.",
        }

    dashboard_tv_symbol = resolve_tv_symbol(selected_asset if selected_asset else "BTC")
    live_market_bias = str(market_snapshot.get("risk_mode", "Neutral")).upper()
    live_ai_confidence = int(market_snapshot.get("ai_confidence", 50) or 50)
    live_market_energy = compute_market_energy_label(market_snapshot.get("total_volume", "..."))
    live_momentum_phase = compute_momentum_phase(market_snapshot.get("market_regime", "Compression"))

    base_query = Signal.query
    if selected_asset:
        base_query = base_query.filter_by(asset=selected_asset)

    all_signals = base_query.order_by(Signal.created_at.asc()).all()

    available_assets = [
        row[0]
        for row in db.session.query(Signal.asset).distinct().order_by(Signal.asset).all()
    ]

    limit = signal_limit_for_plan(user_plan)
    signals = all_signals[-limit:] if limit > 0 else []

    total_signals = len(all_signals)
    total_buy = len([s for s in all_signals if s.action == "BUY"])
    total_sell = len([s for s in all_signals if s.action == "SELL"])

    total_win = len([s for s in all_signals if s.status == "WIN"])
    total_loss = len([s for s in all_signals if s.status == "LOSS"])
    total_open = len([s for s in all_signals if s.status == "OPEN"])

    closed_trades = total_win + total_loss
    calculated_winrate = round((total_win / closed_trades) * 100, 2) if closed_trades > 0 else 0
    last_signal = all_signals[-1] if all_signals else None

    can_view_stats = has_access(user_plan, "advanced_stats")
    can_view_replay = has_access(user_plan, "trade_replays")
    can_view_full_history = has_access(user_plan, "full_history")

    can_view_basic_brief = has_access(user_plan, "morning_brief")
    can_view_premium_brief = has_access(user_plan, "premium_brief_2")
    can_view_vip_brief = has_access(user_plan, "vip_briefings")
    can_view_briefing = can_view_basic_brief or can_view_premium_brief or can_view_vip_brief

    if user_plan == "vip":
        daily_signal_limit = "unlimited"
        sent_today_count = count_sent_today("signal_open", "vip")
        signals_remaining_today = "unlimited"
        quota_progress_pct = 100
        quota_status_label = "Illimité"
    elif user_plan == "premium":
        daily_signal_limit = 10
        sent_today_count = count_sent_today("signal_open", "premium")
        signals_remaining_today = max(0, daily_signal_limit - sent_today_count)
        quota_progress_pct = min(100, int((sent_today_count / daily_signal_limit) * 100)) if daily_signal_limit else 0
        quota_status_label = f"{sent_today_count}/{daily_signal_limit}"
    elif user_plan == "basic":
        daily_signal_limit = 5
        sent_today_count = count_sent_today("signal_open", "basic")
        signals_remaining_today = max(0, daily_signal_limit - sent_today_count)
        quota_progress_pct = min(100, int((sent_today_count / daily_signal_limit) * 100)) if daily_signal_limit else 0
        quota_status_label = f"{sent_today_count}/{daily_signal_limit}"
    else:
        daily_signal_limit = 0
        sent_today_count = 0
        signals_remaining_today = 0
        quota_progress_pct = 0
        quota_status_label = "0/0"

    if can_view_stats:
        estimated_pnl = round(sum(calculate_trade_pnl(s) for s in all_signals), 2)
        winrate = calculated_winrate

        today = datetime.utcnow().date()
        today_signals = [s for s in all_signals if s.created_at.date() == today]
        today_trades = len(today_signals)
        today_wins = sum(1 for s in today_signals if s.status == "WIN")
        today_losses = sum(1 for s in today_signals if s.status == "LOSS")
        today_pnl = round(sum(calculate_trade_pnl(s) for s in today_signals), 2)

        pnl_labels = []
        pnl_values = []
        cumulative_pnl = 0.0

        closed_signals = [s for s in all_signals if s.status in ["WIN", "LOSS"]]
        for idx, s in enumerate(closed_signals, start=1):
            cumulative_pnl += calculate_trade_pnl(s)
            pnl_labels.append(f"Trade {idx}")
            pnl_values.append(round(cumulative_pnl, 2))

        initial_capital = 1000
        capital = initial_capital
        capital_labels = []
        capital_values = []

        for idx, s in enumerate(closed_signals, start=1):
            capital += calculate_trade_pnl(s)
            capital_labels.append(f"Trade {idx}")
            capital_values.append(round(capital, 2))

        current_capital = round(capital, 2)
        capital_return_pct = round(((current_capital - initial_capital) / initial_capital) * 100, 2)
    else:
        estimated_pnl = None
        winrate = None
        today_trades = None
        today_wins = None
        today_losses = None
        today_pnl = None
        pnl_labels = []
        pnl_values = []
        initial_capital = None
        current_capital = None
        capital_return_pct = None
        capital_labels = []
        capital_values = []

    raw_briefing = None
    latest_briefing = None
    briefing_plan_label = None

    if can_view_briefing:
        raw_briefing = ensure_daily_briefing()
        latest_briefing, briefing_plan_label, can_view_briefing = _build_dashboard_brief_preview(
            raw_briefing, user_plan
        )

    latest_replay = None
    if can_view_replay:
        replay_query = TradeReplay.query
        if selected_asset:
            replay_query = replay_query.filter_by(symbol=selected_asset)
        latest_replay = replay_query.order_by(TradeReplay.created_at.desc()).first()

    asset_leaderboard = build_asset_leaderboard(all_signals)

    return render_template(
        "dashboard.html",
        email=current_user.email,
        current_lang=lang_code,
        signals=sorted(signals, key=lambda s: s.created_at, reverse=True),
        total_signals=total_signals,
        total_buy=total_buy,
        total_sell=total_sell,
        total_win=total_win,
        total_loss=total_loss,
        total_open=total_open,
        winrate=winrate,
        last_signal=last_signal,
        estimated_pnl=estimated_pnl,
        today_trades=today_trades,
        today_wins=today_wins,
        today_losses=today_losses,
        today_pnl=today_pnl,
        pnl_labels=pnl_labels,
        pnl_values=pnl_values,
        initial_capital=initial_capital,
        current_capital=current_capital,
        capital_return_pct=capital_return_pct,
        capital_labels=capital_labels,
        capital_values=capital_values,
        is_premium=current_user.is_premium,
        user_plan=user_plan,
        selected_asset=selected_asset,
        available_assets=available_assets,
        latest_briefing=latest_briefing,
        latest_replay=latest_replay,
        can_view_stats=can_view_stats,
        can_view_replay=can_view_replay,
        can_view_briefing=can_view_briefing,
        can_view_full_history=can_view_full_history,
        signal_limit=limit,
        daily_signal_limit=daily_signal_limit,
        sent_today_count=sent_today_count,
        signals_remaining_today=signals_remaining_today,
        quota_progress_pct=quota_progress_pct,
        quota_status_label=quota_status_label,
        briefing_plan_label=briefing_plan_label,
        market_snapshot=market_snapshot,
        dashboard_tv_symbol=dashboard_tv_symbol,
        live_market_bias=live_market_bias,
        live_ai_confidence=live_ai_confidence,
        live_market_energy=live_market_energy,
        live_momentum_phase=live_momentum_phase,
        asset_leaderboard=asset_leaderboard,
    )


@dashboard_bp.route("/<lang_code>/debug-user")
@login_required
def debug_user(lang_code):
    return {
        "email": current_user.email,
        "is_premium": current_user.is_premium,
        "plan": current_user.plan,
        "stripe_customer_id": current_user.stripe_customer_id,
        "stripe_subscription_id": current_user.stripe_subscription_id,
    }


@dashboard_bp.route("/<lang_code>/premium-data")
@login_required
@plan_required("basic")
def premium_data(lang_code):
    return "🔥 Données premium secrètes"


@dashboard_bp.route("/<lang_code>/briefing")
@login_required
@plan_required("basic")
def briefing_page(lang_code):
    briefing = ensure_daily_briefing()
    latest_briefing, briefing_plan_label, can_view_briefing = _build_dashboard_brief_preview(
        briefing, getattr(current_user, "plan", "free")
    )

    if not can_view_briefing or latest_briefing is None:
        return render_template("briefing.html", briefing=None, briefing_plan_label=None)

    return render_template(
        "briefing.html",
        briefing=latest_briefing,
        briefing_plan_label=briefing_plan_label,
    )