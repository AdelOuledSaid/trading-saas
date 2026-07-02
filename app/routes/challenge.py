import re
from datetime import datetime, timezone

from flask import Blueprint, render_template, jsonify, request, abort
from sqlalchemy import desc, or_, and_

from app.extensions import db
from app.models import TradeReplay, Signal, ChallengeScore
from app.routes.replay import (
    _load_primary_candles_for_replay,
    _load_htf_candles_for_replay,
    _next_higher_timeframe,
    _compute_rr,
    _ideal_decision_from_result,
    _score_decision,
)
from app.services.replay_engine_service import build_replay_engine_result

challenge_bp = Blueprint("challenge", __name__)

MAX_CHALLENGES = 8
_PSEUDO_RE = re.compile(r"^[\w \-.]{2,40}$", re.UNICODE)


def _to_unix_seconds(value):
    """lightweight-charts needs intraday time as a Unix timestamp in seconds
    (a number). Candles here carry an ISO string, which the chart would read as
    a business day -> all same-day candles merge into one bar. Convert it."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        return int(v / 1000) if v > 1e12 else int(v)  # ms -> s if needed
    if isinstance(value, datetime):
        return int(value.timestamp())
    try:
        s = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


def _f(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _closed_replays_query():
    """Replays of WINNING signals only (status WIN or positive result).
    Their levels are already public on the Results page, so guests can replay
    them with no premium leak."""
    return (
        TradeReplay.query
        .join(Signal, TradeReplay.signal_id == Signal.id)
        .filter(
            Signal.is_deleted == False,  # noqa: E712
            or_(
                Signal.status == "WIN",
                and_(Signal.result_percent.isnot(None), Signal.result_percent > 0),
            ),
        )
    )


def _is_public_challenge(replay):
    if not replay:
        return False
    sig = Signal.query.get(replay.signal_id)
    if not sig or sig.is_deleted:
        return False
    return bool(
        sig.status == "WIN"
        or (sig.result_percent is not None and sig.result_percent > 0)
    )


def _engine_for(replay):
    tf = (replay.timeframe or "15m").lower()
    _, candles, _, _, _ = _load_primary_candles_for_replay(replay, tf)
    try:
        htf = _load_htf_candles_for_replay(replay, _next_higher_timeframe(tf))
    except Exception:
        htf = []
    engine = build_replay_engine_result(
        candles=candles,
        direction=replay.direction,
        entry_price=replay.entry_price,
        stop_loss=replay.stop_loss,
        take_profit=replay.take_profit,
        entry_time=replay.entry_time,
        base_result=replay.result or "OPEN",
        htf_candles=htf,
    )
    return candles, engine, tf


@challenge_bp.route("/defi")
@challenge_bp.route("/<lang_code>/defi")
def challenge_home(lang_code="fr"):
    replays = _closed_replays_query().order_by(desc(TradeReplay.id)).limit(MAX_CHALLENGES).all()
    challenges = [
        {
            "replay_id": r.id,
            "asset": r.symbol,
            "direction": (r.direction or "").upper(),
            "timeframe": r.timeframe or "15m",
        }
        for r in replays
    ]
    leaderboard = (
        ChallengeScore.query
        .order_by(desc(ChallengeScore.score), ChallengeScore.created_at)
        .limit(15).all()
    )
    return render_template(
        "challenge_home.html",
        challenges=challenges,
        leaderboard=[s.to_public_dict() for s in leaderboard],
    )


@challenge_bp.route("/defi/<int:replay_id>")
@challenge_bp.route("/<lang_code>/defi/<int:replay_id>")
def challenge_play(replay_id, lang_code="fr"):
    replay = TradeReplay.query.get(replay_id)
    if not _is_public_challenge(replay):
        abort(404)
    return render_template(
        "challenge_play.html",
        replay_id=replay_id,
        asset=replay.symbol,
        direction=(replay.direction or "").upper(),
    )


@challenge_bp.route("/api/defi/<int:replay_id>")
@challenge_bp.route("/<lang_code>/api/defi/<int:replay_id>")
def challenge_data(replay_id, lang_code="fr"):
    """Sanitized payload. Deliberately does NOT include the outcome / ideal
    decision, so the answer can't be read before the player chooses."""
    replay = TradeReplay.query.get(replay_id)
    if not _is_public_challenge(replay):
        abort(404)
    try:
        candles, engine, tf = _engine_for(replay)
    except Exception:
        return jsonify({"error": "data_unavailable"}), 503

    slim = []
    for c in candles:
        ts = _to_unix_seconds(c.get("time"))
        if ts is None:
            continue
        slim.append({
            "time": ts,
            "open": _f(c.get("open")),
            "high": _f(c.get("high")),
            "low": _f(c.get("low")),
            "close": _f(c.get("close")),
        })
    return jsonify({
        "asset": replay.symbol,
        "direction": (replay.direction or "").upper(),
        "timeframe": tf,
        "entry_price": replay.entry_price,
        "stop_loss": replay.stop_loss,
        "take_profit": replay.take_profit,
        "entry_index": engine.entry_index,
        "decision_index": engine.decision_index,
        "exit_index": engine.exit_index,
        "candles": slim,
    })


@challenge_bp.route("/api/defi/<int:replay_id>/decision", methods=["POST"])
@challenge_bp.route("/<lang_code>/api/defi/<int:replay_id>/decision", methods=["POST"])
def challenge_decision(replay_id, lang_code="fr"):
    replay = TradeReplay.query.get(replay_id)
    if not _is_public_challenge(replay):
        abort(404)

    data = request.get_json(silent=True) or {}
    choice = (data.get("decision") or "").strip().lower()
    if choice not in ["close", "hold", "partial"]:
        return jsonify({"error": "invalid_decision"}), 400

    try:
        _, engine, _ = _engine_for(replay)
    except Exception:
        return jsonify({"error": "data_unavailable"}), 503

    rr = _compute_rr(replay.entry_price, replay.stop_loss, replay.take_profit) or 1.0
    ideal = _ideal_decision_from_result(engine.derived_result)
    score, status, _status_text = _score_decision(
        choice=choice, ideal_decision=ideal, result=engine.derived_result, rr=rr,
    )
    return jsonify({
        "score": int(score),
        "status": status,
        "ideal_decision": ideal,
        "result": engine.derived_result,
        "exit_index": engine.exit_index,
        "exit_price": engine.exit_price,
        "exit_reason": engine.exit_reason,
        "result_percent": replay.result_percent,
    })


@challenge_bp.route("/api/defi/leaderboard", methods=["GET"])
@challenge_bp.route("/<lang_code>/api/defi/leaderboard", methods=["GET"])
def challenge_leaderboard(lang_code="fr"):
    top = (
        ChallengeScore.query
        .order_by(desc(ChallengeScore.score), ChallengeScore.created_at)
        .limit(15).all()
    )
    return jsonify({"leaderboard": [s.to_public_dict() for s in top]})


@challenge_bp.route("/api/defi/leaderboard", methods=["POST"])
@challenge_bp.route("/<lang_code>/api/defi/leaderboard", methods=["POST"])
def challenge_leaderboard_submit(lang_code="fr"):
    data = request.get_json(silent=True) or {}
    pseudo = (data.get("pseudo") or "").strip()[:40]
    if not pseudo or not _PSEUDO_RE.match(pseudo):
        return jsonify({"error": "invalid_pseudo"}), 400
    try:
        score = int(data.get("score"))
        rounds = int(data.get("rounds") or 1)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_score"}), 400
    if rounds < 1 or rounds > 20 or score < 0 or score > 100 * rounds:
        return jsonify({"error": "out_of_range"}), 400

    db.session.add(ChallengeScore(pseudo=pseudo, score=score, rounds=rounds))
    db.session.commit()

    top = (
        ChallengeScore.query
        .order_by(desc(ChallengeScore.score), ChallengeScore.created_at)
        .limit(15).all()
    )
    return jsonify({"ok": True, "leaderboard": [s.to_public_dict() for s in top]})
