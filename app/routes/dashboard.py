from datetime import datetime
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

dashboard_bp = Blueprint("dashboard", __name__)


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


@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    sync_user_premium_status(current_user)

    user_plan = getattr(current_user, "plan", "free")

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

    # =========================
    # SIGNAL LIMIT BY PLAN
    # Basic = 5 / Premium = 10 / VIP = unlimited
    # =========================
    limit = signal_limit_for_plan(user_plan)
    signals = all_signals[-limit:] if limit > 0 else []

    # =========================
    # BASIC COUNTS
    # =========================
    total_signals = len(all_signals)
    total_buy = len([s for s in all_signals if s.action == "BUY"])
    total_sell = len([s for s in all_signals if s.action == "SELL"])

    total_win = len([s for s in all_signals if s.status == "WIN"])
    total_loss = len([s for s in all_signals if s.status == "LOSS"])
    total_open = len([s for s in all_signals if s.status == "OPEN"])

    closed_trades = total_win + total_loss
    calculated_winrate = round((total_win / closed_trades) * 100, 2) if closed_trades > 0 else 0
    last_signal = all_signals[-1] if all_signals else None

    # =========================
    # ACCESS FLAGS
    # =========================
    can_view_stats = has_access(user_plan, "advanced_stats")
    can_view_replay = has_access(user_plan, "trade_replays")
    can_view_full_history = has_access(user_plan, "full_history")

    # Business logic briefing:
    # Basic = morning_brief
    # Premium = premium_brief_2
    # VIP = vip_briefings
    can_view_basic_brief = has_access(user_plan, "morning_brief")
    can_view_premium_brief = has_access(user_plan, "premium_brief_2")
    can_view_vip_brief = has_access(user_plan, "vip_briefings")
    can_view_briefing = can_view_basic_brief or can_view_premium_brief or can_view_vip_brief

    # =========================
    # LIVE DAILY SIGNAL QUOTA
    # =========================
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

    # =========================
    # ADVANCED STATS
    # =========================
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

    # =========================
    # BRIEFING BY PLAN
    # Basic = simple
    # Premium = full
    # VIP = detailed
    # =========================
    raw_briefing = None
    latest_briefing = None
    briefing_plan_label = None

    if can_view_briefing:
        raw_briefing = ensure_daily_briefing()
        latest_briefing, briefing_plan_label, can_view_briefing = _build_dashboard_brief_preview(
            raw_briefing, user_plan
        )

    # =========================
    # LATEST REPLAY
    # =========================
    latest_replay = None
    if can_view_replay:
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
@plan_required("basic")
def briefing_page():
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