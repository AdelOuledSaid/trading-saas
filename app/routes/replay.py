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


def _safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _compute_rr(entry_price, stop_loss, take_profit):
    entry = _safe_float(entry_price, 0.0)
    sl = _safe_float(stop_loss, 0.0)
    tp = _safe_float(take_profit, 0.0)

    risk = abs(entry - sl)
    reward = abs(tp - entry)

    if risk <= 0:
        return None

    return round(reward / risk, 2)


def _compute_setup_grade(confidence, rr):
    confidence = _safe_float(confidence, 0.0)
    rr = _safe_float(rr, 0.0)

    if confidence >= 80 and rr >= 2:
        return "A+"
    if confidence >= 70 and rr >= 1.5:
        return "A"
    if confidence >= 60 and rr >= 1.2:
        return "B"
    if confidence >= 45:
        return "C"
    return "D"


def _compute_difficulty(confidence, rr, event_count):
    confidence = _safe_float(confidence, 0.0)
    rr = _safe_float(rr, 0.0)

    score = 0

    if confidence < 55:
        score += 1
    if rr < 1.4:
        score += 1
    if event_count >= 6:
        score += 1

    if score == 0:
        return "Easy"
    if score == 1:
        return "Intermediate"
    return "Advanced"


def _ideal_decision_from_result(result):
    result = (result or "").upper()

    if result == "WIN":
        return "hold"
    if result == "BREAKEVEN":
        return "partial"
    if result == "LOSS":
        return "close"
    return "hold"


def _decision_label(decision):
    mapping = {
        "hold": "Conserver",
        "partial": "Alléger",
        "close": "Fermer"
    }
    return mapping.get(decision, decision)


def _score_decision(choice, ideal_decision, result, rr):
    rr = _safe_float(rr, 1.0)
    result = (result or "").upper()

    if choice == ideal_decision:
        return 10, "good", "Excellente décision"

    if ideal_decision == "hold" and choice == "partial":
        return 6, "medium", "Gestion prudente"

    if ideal_decision == "partial" and choice == "hold":
        return 5, "medium", "Choix défendable mais agressif"

    if ideal_decision == "partial" and choice == "close":
        return 3, "bad", "Sortie trop conservatrice"

    if ideal_decision == "close" and choice == "partial":
        return 4, "medium", "Tu limites la casse mais tu restes exposé"

    if ideal_decision == "close" and choice == "hold":
        return 0, "bad", "Tu ignores l’invalidation du setup"

    if ideal_decision == "hold" and choice == "close":
        if rr >= 2:
            return 1, "bad", "Sortie émotionnelle sur un setup à fort potentiel"
        return 2, "bad", "Tu coupes trop tôt"

    return 4, "medium", "Décision acceptable mais non optimale"


def _feedback_message(choice, ideal_decision, result):
    if choice == ideal_decision:
        if choice == "hold":
            return "✅ Très bon choix. Le plan de trade devait être respecté malgré la pression du marché."
        if choice == "partial":
            return "✅ Bonne lecture. Sécuriser partiellement était la meilleure réponse dans ce contexte."
        return "✅ Bonne décision. Le setup était invalidé, sortir protégeait le capital."

    if ideal_decision == "hold":
        return "⚠️ Le setup n’était pas encore invalidé. Un trader discipliné laissait davantage respirer la position."
    if ideal_decision == "partial":
        return "⚠️ Le contexte appelait une gestion intermédiaire. Tout couper ou tout laisser courir n’était pas optimal."
    return "❌ Le marché ne validait plus le scénario initial. Il fallait réduire fortement le risque ou sortir."


@replay_bp.route("/replay/<int:replay_id>")
@replay_bp.route("/<lang_code>/replay/<int:replay_id>")
def replay_page(replay_id, lang_code="fr"):
    replay = TradeReplay.query.get(replay_id)

    if not replay:
        abort(404)

    return render_template(
        "replay.html",
        replay=replay,
        current_lang=lang_code
    )


@replay_bp.route("/api/replay/<int:replay_id>")
@replay_bp.route("/<lang_code>/api/replay/<int:replay_id>")
def replay_data(replay_id, lang_code="fr"):
    replay = TradeReplay.query.get(replay_id)

    if not replay:
        return jsonify({"error": "Replay introuvable"}), 404

    candles = ReplayCandle.query.filter_by(
        trade_replay_id=replay.id
    ).order_by(ReplayCandle.position_index.asc()).all()

    events = ReplayEvent.query.filter_by(
        trade_replay_id=replay.id
    ).order_by(ReplayEvent.position_index.asc()).all()

    rr_value = _compute_rr(replay.entry_price, replay.stop_loss, replay.take_profit)
    confidence_value = getattr(replay, "confidence", 0) or 0
    risk_reward_value = getattr(replay, "risk_reward", None) or rr_value or 0
    setup_grade = _compute_setup_grade(confidence_value, risk_reward_value)
    difficulty = _compute_difficulty(confidence_value, risk_reward_value, len(events))

    decision_event = None
    for event in events:
        event_type = (event.event_type or "").lower()
        if event_type in ["decision", "decision_point", "management", "pullback"]:
            decision_event = event
            break

    if decision_event:
        decision_index = decision_event.position_index
    else:
        decision_index = 20 if len(candles) > 25 else max(3, len(candles) // 2)

    ideal_decision = _ideal_decision_from_result(replay.result)

    lessons = [
        "Toujours comparer la réaction du prix au plan initial, pas à l’émotion du moment.",
        "Un bon replay sert à renforcer la discipline, pas seulement à montrer un gain.",
        "La vraie qualité d’un trade se mesure autant dans la gestion que dans l’entrée."
    ]

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
            "post_analysis": replay.post_analysis,
            "confidence": confidence_value,
            "trend": getattr(replay, "trend", None),
            "risk_reward": risk_reward_value,
            "computed_rr": rr_value,
            "setup_grade": setup_grade,
            "difficulty": difficulty,
            "ideal_decision": ideal_decision,
            "ideal_decision_label": _decision_label(ideal_decision),
            "decision_index": decision_index,
            "is_premium": True,
            "lessons": lessons
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
@replay_bp.route("/<lang_code>/api/replay/<int:replay_id>/decision", methods=["POST"])
@login_required
def save_replay_decision(replay_id, lang_code="fr"):
    replay = TradeReplay.query.get(replay_id)

    if not replay:
        return jsonify({"error": "Replay introuvable"}), 404

    data = request.get_json() or {}
    decision = (data.get("decision") or "").strip().lower()

    if decision not in ["close", "hold", "partial"]:
        return jsonify({"error": "Décision invalide"}), 400

    existing = UserReplayDecision.query.filter_by(
        user_id=current_user.id,
        trade_replay_id=replay.id
    ).order_by(UserReplayDecision.created_at.desc()).first()

    rr_value = _compute_rr(
        replay.entry_price,
        replay.stop_loss,
        replay.take_profit
    ) or getattr(replay, "risk_reward", 1)

    ideal_decision = _ideal_decision_from_result(replay.result)

    score, status, status_text = _score_decision(
        choice=decision,
        ideal_decision=ideal_decision,
        result=replay.result,
        rr=rr_value
    )
    feedback = _feedback_message(decision, ideal_decision, replay.result)

    try:
        if existing:
            existing.decision = decision
            existing.score = int(score)
            existing.status = status
            existing.feedback = feedback
        else:
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
            "message": "Décision sauvegardée",
            "score": int(score),
            "status": status,
            "status_text": status_text,
            "feedback": feedback,
            "ideal_decision": ideal_decision,
            "ideal_decision_label": _decision_label(ideal_decision)
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "error": "Erreur sauvegarde",
            "details": str(e)
        }), 500


@replay_bp.route("/api/replay/<int:replay_id>/tv")
@replay_bp.route("/<lang_code>/api/replay/<int:replay_id>/tv")
def replay_tv_data(replay_id, lang_code="fr"):
    replay = TradeReplay.query.get(replay_id)

    if not replay:
        return jsonify({"error": "Replay introuvable"}), 404

    candles = ReplayCandle.query.filter_by(
        trade_replay_id=replay.id
    ).order_by(ReplayCandle.position_index.asc()).all()

    data = []
    for candle in candles:
        if not candle.candle_time:
            continue

        data.append({
            "time": int(candle.candle_time.timestamp()),
            "open": float(candle.open),
            "high": float(candle.high),
            "low": float(candle.low),
            "close": float(candle.close),
            "volume": float(candle.volume or 0)
        })

    return jsonify({
        "symbol": replay.symbol,
        "timeframe": replay.timeframe,
        "data": data
    })


@replay_bp.route("/my-performance")
@replay_bp.route("/<lang_code>/my-performance")
@login_required
def my_performance(lang_code="fr"):
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
        trader_level=trader_level,
        current_lang=lang_code
    )