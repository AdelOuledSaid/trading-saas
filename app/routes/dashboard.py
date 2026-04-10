from datetime import datetime
from flask import Blueprint, render_template, request
from flask_login import login_required, current_user

import config
from app.extensions import db
from app.models import Signal
from app.models.replay import TradeReplay
from app.core.decorators import plan_required
from app.services.signal_service import calculate_trade_pnl
from app.services.stripe_service import sync_user_premium_status, user_has_plan
from app.services.briefing_service import ensure_daily_briefing

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    sync_user_premium_status(current_user)

    selected_asset = request.args.get("asset", "").strip().upper()
    if selected_asset and selected_asset not in config.ALLOWED_ASSETS:
        selected_asset = ""

    base_query = Signal.query
    if selected_asset:
        base_query = base_query.filter_by(asset=selected_asset)

    all_signals = base_query.order_by(Signal.created_at.asc()).all()

    available_assets = [
        row[0]
        for row in db.session.query(Signal.asset).distinct().order_by(Signal.asset).all()
    ]

    if current_user.is_premium:
        signals = all_signals
    else:
        signals = all_signals[-5:]

    total_signals = len(all_signals)
    total_buy = len([s for s in all_signals if s.action == "BUY"])
    total_sell = len([s for s in all_signals if s.action == "SELL"])

    total_win = len([s for s in all_signals if s.status == "WIN"])
    total_loss = len([s for s in all_signals if s.status == "LOSS"])
    total_open = len([s for s in all_signals if s.status == "OPEN"])

    closed_trades = total_win + total_loss
    winrate = round((total_win / closed_trades) * 100, 2) if closed_trades > 0 else 0

    last_signal = all_signals[-1] if all_signals else None
    estimated_pnl = round(sum(calculate_trade_pnl(s) for s in all_signals), 2)

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

    latest_briefing = None
    if user_has_plan(current_user, "premium"):
        latest_briefing = ensure_daily_briefing()

    # =========================
    # LATEST REPLAY
    # =========================
    replay_query = TradeReplay.query
    if selected_asset:
        replay_query = replay_query.filter_by(symbol=selected_asset)

    latest_replay = replay_query.order_by(TradeReplay.created_at.desc()).first()

    return render_template(
        "dashboard.html",
        email=current_user.email,
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
        user_plan=current_user.plan,
        selected_asset=selected_asset,
        available_assets=available_assets,
        latest_briefing=latest_briefing,
        latest_replay=latest_replay
    )


@dashboard_bp.route("/debug-user")
@login_required
def debug_user():
    return {
        "email": current_user.email,
        "is_premium": current_user.is_premium,
        "plan": current_user.plan,
        "stripe_customer_id": current_user.stripe_customer_id,
        "stripe_subscription_id": current_user.stripe_subscription_id,
    }


@dashboard_bp.route("/premium-data")
@login_required
@plan_required("basic")
def premium_data():
    return "🔥 Données premium secrètes"


@dashboard_bp.route("/briefing")
@login_required
@plan_required("premium")
def briefing_page():
    briefing = ensure_daily_briefing()
    return render_template("briefing.html", briefing=briefing)