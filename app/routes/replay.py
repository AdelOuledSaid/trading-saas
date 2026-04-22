from datetime import datetime, timedelta, timezone

from flask import Blueprint, render_template, jsonify, abort, request, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import func

from app.extensions import db
from app.models import Signal
from app.models.replay import TradeReplay, UserReplayDecision
from app.services.replay_recorder_service import ensure_trade_replay_for_signal
from app.services.universal_candles_service import fetch_candles
from app.services.replay_engine_service import build_replay_engine_result

replay_bp = Blueprint("replay", __name__)


# =========================
# HELPERS
# =========================
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

    if confidence >= 85 and rr >= 2.5:
        return "A+"
    if confidence >= 75 and rr >= 2:
        return "A"
    if confidence >= 65 and rr >= 1.5:
        return "B"
    if confidence >= 50:
        return "C"
    return "D"


def _compute_difficulty(confidence, rr, event_count):
    confidence = _safe_float(confidence, 0.0)
    rr = _safe_float(rr, 0.0)

    score = 0
    if confidence < 55:
        score += 1
    if rr < 1.5:
        score += 1
    if event_count >= 5:
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
        "close": "Fermer",
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


def _status_label(status):
    status = (status or "").lower()
    mapping = {
        "good": "Excellente décision",
        "medium": "Décision moyenne",
        "bad": "Mauvaise décision",
    }
    return mapping.get(status, "Décision analysée")


def _compute_timing_score(score):
    base = int(score or 0)
    return max(0, min(10, base - 1 if base >= 8 else base - 2))


def _next_higher_timeframe(timeframe):
    tf = (timeframe or "").lower()
    mapping = {
        "1m": "5m",
        "5m": "15m",
        "15m": "1h",
        "30m": "4h",
        "1h": "4h",
        "4h": "1d",
        "1d": "1d",
    }
    return mapping.get(tf, "1h")


def _normalize_candles(raw_candles):
    normalized = []
    for idx, candle in enumerate(raw_candles or []):
        normalized.append({
            "time": candle.get("time"),
            "open": _safe_float(candle.get("open")),
            "high": _safe_float(candle.get("high")),
            "low": _safe_float(candle.get("low")),
            "close": _safe_float(candle.get("close")),
            "volume": _safe_float(candle.get("volume"), None) if candle.get("volume") is not None else None,
            "index": idx,
        })
    return normalized


def _find_index_by_time(candles, target_time):
    if not candles or not target_time:
        return 0

    if isinstance(target_time, str):
        try:
            target_time = datetime.fromisoformat(target_time)
        except Exception:
            return 0

    if target_time.tzinfo is None:
        target_time = target_time.replace(tzinfo=timezone.utc)

    target_ts = target_time.timestamp()

    best_idx = 0
    best_diff = None

    for candle in candles:
        try:
            candle_dt = datetime.fromisoformat(str(candle.get("time")))
            if candle_dt.tzinfo is None:
                candle_dt = candle_dt.replace(tzinfo=timezone.utc)

            diff = abs(candle_dt.timestamp() - target_ts)
            if best_diff is None or diff < best_diff:
                best_diff = diff
                best_idx = candle["index"]
        except Exception:
            continue

    return best_idx


def _trim_centered_on_entry(candles, entry_time, max_count=140, pre_bars=20):
    if not candles:
        return []

    if len(candles) <= max_count:
        out = []
        for idx, candle in enumerate(candles):
            copy = dict(candle)
            copy["index"] = idx
            out.append(copy)
        return out

    entry_idx = _find_index_by_time(candles, entry_time)

    start = max(0, entry_idx - pre_bars)
    end = min(len(candles), start + max_count)

    if end - start < max_count:
        start = max(0, end - max_count)

    trimmed = candles[start:end]

    out = []
    for idx, candle in enumerate(trimmed):
        copy = dict(candle)
        copy["index"] = idx
        out.append(copy)

    return out


def _build_htf_zones(htf_candles):
    if not htf_candles or len(htf_candles) < 4:
        return []

    highs = [_safe_float(c["high"]) for c in htf_candles[-12:]]
    lows = [_safe_float(c["low"]) for c in htf_candles[-12:]]

    if not highs or not lows:
        return []

    recent_high = max(highs)
    recent_low = min(lows)
    zone_size = (recent_high - recent_low) * 0.18

    if zone_size <= 0:
        return []

    supply = {
        "label": "HTF Supply",
        "low": round(recent_high - zone_size, 6),
        "high": round(recent_high, 6),
    }

    demand = {
        "label": "HTF Demand",
        "low": round(recent_low, 6),
        "high": round(recent_low + zone_size, 6),
    }

    return [supply, demand]


def _build_lessons_from_engine(engine):
    lessons = [
        f"Structure détectée : {engine.market_structure}.",
        f"Biais HTF : {engine.htf_bias}.",
        f"État du trade au moment de décision : {engine.trade_health}.",
        engine.decision_context,
    ]

    if engine.max_favorable_excursion_percent is not None:
        lessons.append(f"MFE : {engine.max_favorable_excursion_percent}%.")

    if engine.max_adverse_excursion_percent is not None:
        lessons.append(f"MAE : {engine.max_adverse_excursion_percent}%.")

    return lessons


def _history_window_for_replay(replay):
    entry_dt = replay.entry_time or replay.replay_start or datetime.now(timezone.utc)
    if entry_dt.tzinfo is None:
        entry_dt = entry_dt.replace(tzinfo=timezone.utc)

    replay_end = replay.replay_end or (entry_dt + timedelta(hours=36))
    if replay_end.tzinfo is None:
        replay_end = replay_end.replace(tzinfo=timezone.utc)

    start_dt = entry_dt - timedelta(hours=8)
    end_dt = replay_end + timedelta(hours=8)

    return start_dt, end_dt


def _load_primary_candles_for_replay(replay, timeframe):
    start_dt, end_dt = _history_window_for_replay(replay)

    raw = fetch_candles(
        asset=replay.symbol,
        timeframe=timeframe,
        limit=800,
        start_time=start_dt,
        end_time=end_dt,
    )

    candles = _normalize_candles(raw)
    candles = _trim_centered_on_entry(
        candles,
        entry_time=replay.entry_time,
        max_count=140,
        pre_bars=24,
    )

    return raw, candles, start_dt, end_dt


def _load_htf_candles_for_replay(replay, higher_tf):
    start_dt, end_dt = _history_window_for_replay(replay)

    raw = fetch_candles(
        asset=replay.symbol,
        timeframe=higher_tf,
        limit=300,
        start_time=start_dt - timedelta(hours=24),
        end_time=end_dt + timedelta(hours=24),
    )

    return _normalize_candles(raw)


# =========================
# ROUTES
# =========================
@replay_bp.route("/signal/<int:signal_id>/replay")
@replay_bp.route("/<lang_code>/signal/<int:signal_id>/replay")
@login_required
def open_signal_replay(signal_id, lang_code="fr"):
    signal = Signal.query.get_or_404(signal_id)

    replay = ensure_trade_replay_for_signal(signal)

    if not replay:
        abort(404)

    return redirect(
        url_for(
            "replay.replay_page",
            replay_id=replay.id,
            lang_code=lang_code,
        )
    )


@replay_bp.route("/replay/<int:replay_id>")
@replay_bp.route("/<lang_code>/replay/<int:replay_id>")
@login_required
def replay_page(replay_id, lang_code="fr"):
    replay = TradeReplay.query.get(replay_id)

    if not replay:
        abort(404)

    return render_template(
        "replay.html",
        replay=replay,
        current_lang=lang_code,
    )


@replay_bp.route("/api/replay/<int:replay_id>")
@replay_bp.route("/<lang_code>/api/replay/<int:replay_id>")
@login_required
def replay_data(replay_id, lang_code="fr"):
    replay = TradeReplay.query.get(replay_id)

    if not replay:
        return jsonify({"error": "Replay introuvable"}), 404

    primary_tf = (replay.timeframe or "15m").lower()
    higher_tf = _next_higher_timeframe(primary_tf)

    try:
        primary_raw, primary_candles, start_dt, end_dt = _load_primary_candles_for_replay(replay, primary_tf)
        htf_candles = _load_htf_candles_for_replay(replay, higher_tf)
    except Exception as e:
        return jsonify({"error": f"Erreur données marché: {str(e)}"}), 500

    if primary_raw is None or not isinstance(primary_raw, list) or len(primary_raw) == 0:
        return jsonify({
            "error": "Aucune donnée marché disponible",
            "debug": {
                "symbol": replay.symbol,
                "timeframe": primary_tf,
            }
        }), 404

    if not primary_candles:
        return jsonify({
            "error": "Impossible de construire le replay: aucune bougie exploitable.",
            "debug": {
                "symbol": replay.symbol,
                "timeframe": primary_tf,
                "raw_len": len(primary_raw),
                "window_start": start_dt.isoformat(),
                "window_end": end_dt.isoformat(),
            }
        }), 400

    first_candle_time = primary_candles[0]["time"]
    last_candle_time = primary_candles[-1]["time"]

    engine = build_replay_engine_result(
        candles=primary_candles,
        direction=replay.direction,
        entry_price=replay.entry_price,
        stop_loss=replay.stop_loss,
        take_profit=replay.take_profit,
        entry_time=replay.entry_time,
        base_result=replay.result or "OPEN",
        htf_candles=htf_candles,
    )

    events = engine.events
    timeline = engine.timeline

    rr_value = _compute_rr(replay.entry_price, replay.stop_loss, replay.take_profit)
    confidence_value = getattr(replay, "confidence", 0) or 0
    risk_reward_value = getattr(replay, "risk_reward", None) or rr_value or 0
    setup_grade = _compute_setup_grade(confidence_value, risk_reward_value)
    difficulty = _compute_difficulty(confidence_value, risk_reward_value, len(events))
    ideal_decision = _ideal_decision_from_result(engine.derived_result)
    htf_zones = _build_htf_zones(htf_candles)
    lessons = _build_lessons_from_engine(engine)

    return jsonify({
        "trade": {
            "id": replay.id,
            "signal_id": replay.signal_id,
            "symbol": replay.symbol,
            "timeframe": primary_tf,
            "higher_timeframe": higher_tf,
            "direction": replay.direction,
            "replay_start": replay.replay_start.isoformat() if replay.replay_start else None,
            "replay_end": replay.replay_end.isoformat() if replay.replay_end else None,
            "entry_time": replay.entry_time.isoformat() if replay.entry_time else None,
            "exit_time": replay.exit_time.isoformat() if replay.exit_time else None,
            "entry_price": _safe_float(replay.entry_price, 0),
            "stop_loss": _safe_float(replay.stop_loss, 0),
            "take_profit": _safe_float(replay.take_profit, 0),
            "result": engine.derived_result,
            "derived_result": engine.derived_result,
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
            "decision_index": engine.decision_index,
            "entry_index": engine.entry_index,
            "exit_index": engine.exit_index,
            "entry_time_engine": engine.entry_time,
            "decision_time": engine.decision_time,
            "exit_time_engine": engine.exit_time,
            "exit_reason": engine.exit_reason,
            "exit_price": engine.exit_price,
            "trade_health": engine.trade_health,
            "market_structure": engine.market_structure,
            "distance_to_sl_percent": engine.distance_to_sl_percent,
            "distance_to_tp_percent": engine.distance_to_tp_percent,
            "max_favorable_excursion_percent": engine.max_favorable_excursion_percent,
            "max_adverse_excursion_percent": engine.max_adverse_excursion_percent,
            "live_outcome_if_hold": engine.live_outcome_if_hold,
            "decision_context": engine.decision_context,
            "should_stop_replay_at_exit": engine.should_stop_replay_at_exit,
            "sl_hit": {
                "index": engine.sl_hit.index,
                "time": engine.sl_hit.time,
                "price": engine.sl_hit.price,
                "reason": engine.sl_hit.reason,
            },
            "tp_hit": {
                "index": engine.tp_hit.index,
                "time": engine.tp_hit.time,
                "price": engine.tp_hit.price,
                "reason": engine.tp_hit.reason,
            },
            "is_premium": True,
            "lessons": lessons,
            "timeline": timeline,
            "user_hint_before_decision": engine.decision_context,
            "desk_note": "Respect du plan, gestion du risque et lecture du contexte priment sur l’émotion.",
            "htf_bias": engine.htf_bias,
            "htf_zones": htf_zones,
        },
        "debug": {
            "raw_len": len(primary_raw),
            "final_len": len(primary_candles),
            "symbol": replay.symbol,
            "timeframe": primary_tf,
            "window_start": start_dt.isoformat(),
            "window_end": end_dt.isoformat(),
            "first_candle_time": first_candle_time,
            "last_candle_time": last_candle_time,
            "entry_time": replay.entry_time.isoformat() if replay.entry_time else None,
        },
        "candles": primary_candles,
        "higher_timeframe_candles": htf_candles,
        "events": events,
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
        trade_replay_id=replay.id,
    ).order_by(UserReplayDecision.created_at.desc()).first()

    primary_tf = (replay.timeframe or "15m").lower()
    higher_tf = _next_higher_timeframe(primary_tf)

    try:
        _, primary_candles, _, _ = _load_primary_candles_for_replay(replay, primary_tf)
        htf_candles = _load_htf_candles_for_replay(replay, higher_tf)
    except Exception as e:
        return jsonify({"error": f"Erreur données marché: {str(e)}"}), 500

    engine = build_replay_engine_result(
        candles=primary_candles,
        direction=replay.direction,
        entry_price=replay.entry_price,
        stop_loss=replay.stop_loss,
        take_profit=replay.take_profit,
        entry_time=replay.entry_time,
        base_result=replay.result or "OPEN",
        htf_candles=htf_candles,
    )

    rr_value = _compute_rr(
        replay.entry_price,
        replay.stop_loss,
        replay.take_profit,
    ) or getattr(replay, "risk_reward", 1)

    ideal_decision = _ideal_decision_from_result(engine.derived_result)

    score, status, status_text = _score_decision(
        choice=decision,
        ideal_decision=ideal_decision,
        result=engine.derived_result,
        rr=rr_value,
    )
    feedback = _feedback_message(decision, ideal_decision, engine.derived_result)
    timing_score = _compute_timing_score(score)

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
                feedback=feedback,
            )
            db.session.add(new_decision)

        db.session.commit()

        user_avg_score = db.session.query(
            func.avg(UserReplayDecision.score)
        ).filter(
            UserReplayDecision.user_id == current_user.id
        ).scalar()

        user_avg_score = round(float(user_avg_score), 1) if user_avg_score is not None else 0.0
        estimated_percentile = min(99, max(1, int((score / 10) * 100) - 8))

        return jsonify({
            "success": True,
            "message": "Décision sauvegardée",
            "score": int(score),
            "status": status,
            "status_text": status_text,
            "status_label": _status_label(status),
            "feedback": feedback,
            "ideal_decision": ideal_decision,
            "ideal_decision_label": _decision_label(ideal_decision),
            "discipline_score": int(score),
            "timing_score": int(timing_score),
            "user_avg_score": user_avg_score,
            "estimated_percentile": estimated_percentile,
            "comparison_text": f"Tu fais mieux que {estimated_percentile}% des traders sur cette décision.",
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "error": "Erreur sauvegarde",
            "details": str(e),
        }), 500


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
        status="good",
    ).count()

    medium_count = UserReplayDecision.query.filter_by(
        user_id=current_user.id,
        status="medium",
    ).count()

    bad_count = UserReplayDecision.query.filter_by(
        user_id=current_user.id,
        status="bad",
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
        current_lang=lang_code,
    )