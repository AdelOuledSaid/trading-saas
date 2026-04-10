from flask import Blueprint, render_template, jsonify, abort, request
from flask_login import login_required, current_user
from sqlalchemy import func

from app.extensions import db
from app.models.replay import (
    TradeReplay,
    ReplayCandle,
    ReplayEvent,
    UserReplayDecision
)

replay_bp = Blueprint("replay", __name__)


@replay_bp.route("/replay/<int:replay_id>")
def replay_page(replay_id):
    replay = TradeReplay.query.get(replay_id)

    if not replay:
        abort(404)

    return render_template("replay.html", replay=replay)


@replay_bp.route("/api/replay/<int:replay_id>")
def replay_data(replay_id):
    replay = TradeReplay.query.get(replay_id)

    if not replay:
        return jsonify({"error": "Replay introuvable"}), 404

    candles = ReplayCandle.query.filter_by(
        trade_replay_id=replay.id
    ).order_by(ReplayCandle.position_index.asc()).all()

    events = ReplayEvent.query.filter_by(
        trade_replay_id=replay.id
    ).order_by(ReplayEvent.position_index.asc()).all()

    return jsonify({
        "trade": {
            "id": replay.id,
            "signal_id": replay.signal_id,
            "symbol": replay.symbol,
            "timeframe": replay.timeframe,
            "direction": replay.direction,
            "replay_start": replay.replay_start.isoformat() if replay.replay_start else None,
            "replay_end": replay.replay_end.isoformat() if replay.replay_end else None,
            "entry_time": replay.entry_time.isoformat() if replay.entry_time else None,
            "exit_time": replay.exit_time.isoformat() if replay.exit_time else None,
            "entry_price": replay.entry_price,
            "stop_loss": replay.stop_loss,
            "take_profit": replay.take_profit,
            "result": replay.result,
            "result_percent": replay.result_percent,
            "market_context": replay.market_context,
            "post_analysis": replay.post_analysis
        },
        "candles": [
            {
                "time": candle.candle_time.isoformat() if candle.candle_time else None,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "index": candle.position_index
            }
            for candle in candles
        ],
        "events": [
            {
                "id": event.id,
                "time": event.event_time.isoformat() if event.event_time else None,
                "type": event.event_type,
                "title": event.title,
                "description": event.description,
                "price_level": event.price_level,
                "index": event.position_index
            }
            for event in events
        ]
    })


@replay_bp.route("/api/replay/<int:replay_id>/decision", methods=["POST"])
@login_required
def save_replay_decision(replay_id):
    replay = TradeReplay.query.get(replay_id)

    if not replay:
        return jsonify({"error": "Replay introuvable"}), 404

    data = request.get_json() or {}

    decision = data.get("decision")
    score = data.get("score", 0)
    status = data.get("status")
    feedback = data.get("feedback")

    if decision not in ["close", "hold", "partial"]:
        return jsonify({"error": "Décision invalide"}), 400

    try:
        new_decision = UserReplayDecision(
            user_id=current_user.id,
            trade_replay_id=replay.id,
            decision=decision,
            score=int(score),
            status=status,
            feedback=feedback
        )

        db.session.add(new_decision)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Décision sauvegardée"
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "error": "Erreur sauvegarde",
            "details": str(e)
        }), 500


@replay_bp.route("/my-performance")
@login_required
def my_performance():
    decisions = UserReplayDecision.query.filter_by(
        user_id=current_user.id
    ).order_by(UserReplayDecision.created_at.desc()).all()

    total_decisions = len(decisions)

    avg_score = db.session.query(
        func.avg(UserReplayDecision.score)
    ).filter(
        UserReplayDecision.user_id == current_user.id
    ).scalar()

    avg_score = round(float(avg_score), 1) if avg_score is not None else 0

    good_count = UserReplayDecision.query.filter_by(
        user_id=current_user.id,
        status="good"
    ).count()

    medium_count = UserReplayDecision.query.filter_by(
        user_id=current_user.id,
        status="medium"
    ).count()

    bad_count = UserReplayDecision.query.filter_by(
        user_id=current_user.id,
        status="bad"
    ).count()

    success_rate = round((good_count / total_decisions) * 100, 1) if total_decisions > 0 else 0

    if avg_score >= 8:
        trader_level = "Pro Trader"
    elif avg_score >= 5:
        trader_level = "Intermediate"
    else:
        trader_level = "Beginner"

    return render_template(
        "my_performance.html",
        decisions=decisions,
        total_decisions=total_decisions,
        avg_score=avg_score,
        good_count=good_count,
        medium_count=medium_count,
        bad_count=bad_count,
        success_rate=success_rate,
        trader_level=trader_level
    )