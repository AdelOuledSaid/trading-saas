from datetime import datetime
from flask import Blueprint, request, jsonify, current_app

import config

from app.extensions import db
from app.models import Signal
from app.services.signal_service import close_signal_as_result
from app.services.telegram_dispatcher import (
    send_signal_open,
    send_signal_tp,
    send_signal_sl,
)

manual_signal_bp = Blueprint("manual_signal", __name__)


ALLOWED_ASSETS = {
    "BTCUSD",
    "ETHUSD",
    "SOLUSD",
    "XRPUSD",
    "GOLD",
    "US100",
    "US500",
    "FRA40",
}

ALLOWED_ACTIONS = {"BUY", "SELL"}
ALLOWED_CLOSE_EVENTS = {"TP", "SL"}


def _safe_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_str(value, default=""):
    if value is None:
        return default
    return str(value).strip()


def _build_trade_id(asset: str, action: str) -> str:
    return f"MANUAL-{asset}-{action}-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"


def _validate_prices(action: str, entry: float, sl: float, tp: float):
    if action == "BUY":
        return sl < entry < tp
    if action == "SELL":
        return tp < entry < sl
    return False


def _compute_risk_reward(entry_price: float, stop_loss: float, take_profit: float):
    try:
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
        if risk <= 0:
            return None
        return round(reward / risk, 2)
    except Exception:
        return None


@manual_signal_bp.route("/api/manual-signal", methods=["POST"])
def create_manual_signal():
    data = request.get_json(silent=True) or {}

    # Security
    if not getattr(config, "MANUAL_SIGNAL_SECRET", None):
        current_app.logger.warning("MANUAL_SIGNAL_SECRET manquant dans config.py")
        return jsonify({"error": "Server configuration error"}), 500

    if data.get("secret") != config.MANUAL_SIGNAL_SECRET:
        current_app.logger.warning("Manual signal secret invalide")
        return jsonify({"error": "Unauthorized"}), 403

    asset = _safe_str(data.get("asset")).upper()
    action = _safe_str(data.get("action")).upper()
    entry_price = _safe_float(data.get("entry_price"))
    stop_loss = _safe_float(data.get("stop_loss"))
    take_profit = _safe_float(data.get("take_profit"))

    timeframe = _safe_str(data.get("timeframe")) or "manual"
    signal_type = _safe_str(data.get("signal_type")) or "manual"
    market_trend = _safe_str(data.get("trend")) or None
    setup_note = _safe_str(data.get("setup_note")) or "Manual signal"
    confidence = _safe_float(data.get("confidence"), 80)
    news_sentiment = _safe_float(data.get("news_sentiment"))

    if asset not in ALLOWED_ASSETS:
        return jsonify({"error": f"Invalid asset: {asset}"}), 400

    if action not in ALLOWED_ACTIONS:
        return jsonify({"error": f"Invalid action: {action}"}), 400

    if entry_price is None or stop_loss is None or take_profit is None:
        return jsonify({"error": "entry_price, stop_loss and take_profit are required"}), 400

    if entry_price <= 0 or stop_loss <= 0 or take_profit <= 0:
        return jsonify({"error": "Prices must be greater than 0"}), 400

    if not _validate_prices(action, entry_price, stop_loss, take_profit):
        if action == "BUY":
            return jsonify({"error": "For BUY: stop_loss < entry_price < take_profit"}), 400
        return jsonify({"error": "For SELL: take_profit < entry_price < stop_loss"}), 400

    trade_id = _build_trade_id(asset, action)

    signal = Signal(
        trade_id=trade_id,
        asset=asset,
        action=action,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        status="OPEN",
        timeframe=timeframe,
        signal_type=signal_type,
        market_trend=market_trend,
        source="manual",
        reason=setup_note,
        confidence=confidence,
        news_sentiment=news_sentiment,
    )

    rr = _compute_risk_reward(entry_price, stop_loss, take_profit)

    try:
        if hasattr(signal, "update_risk_reward"):
            signal.update_risk_reward()
        elif hasattr(signal, "compute_rr"):
            signal.risk_reward = signal.compute_rr()
        elif hasattr(signal, "risk_reward"):
            signal.risk_reward = rr
    except Exception:
        if hasattr(signal, "risk_reward"):
            signal.risk_reward = rr

    db.session.add(signal)
    db.session.commit()

    telegram_results = None
    telegram_error = None

    try:
        telegram_results = send_signal_open(signal)
        current_app.logger.info(
            "Manual OPEN envoyé | trade_id=%s | results=%s",
            signal.trade_id,
            telegram_results,
        )
    except Exception as e:
        telegram_error = str(e)
        current_app.logger.warning(
            "Erreur Telegram OPEN manual | trade_id=%s | error=%s",
            signal.trade_id,
            e,
        )

    return jsonify({
        "status": "ok",
        "message": "Manual signal created",
        "signal": {
            "id": signal.id,
            "trade_id": signal.trade_id,
            "asset": signal.asset,
            "action": signal.action,
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "status": signal.status,
            "timeframe": signal.timeframe,
            "signal_type": signal.signal_type,
            "source": signal.source,
            "risk_reward": getattr(signal, "risk_reward", rr),
            "reason": signal.reason,
            "confidence": signal.confidence,
            "created_at": signal.created_at.isoformat() if getattr(signal, "created_at", None) else None,
        },
        "telegram_sent": telegram_error is None,
        "telegram_results": telegram_results,
        "telegram_error": telegram_error,
    }), 201


@manual_signal_bp.route("/api/manual-signal/<int:signal_id>/close", methods=["POST"])
def close_manual_signal(signal_id):
    data = request.get_json(silent=True) or {}

    if not getattr(config, "MANUAL_SIGNAL_SECRET", None):
        current_app.logger.warning("MANUAL_SIGNAL_SECRET manquant dans config.py")
        return jsonify({"error": "Server configuration error"}), 500

    if data.get("secret") != config.MANUAL_SIGNAL_SECRET:
        current_app.logger.warning("Manual close secret invalide")
        return jsonify({"error": "Unauthorized"}), 403

    event_type = _safe_str(data.get("event")).upper()

    if event_type not in ALLOWED_CLOSE_EVENTS:
        return jsonify({"error": "Invalid event. Use TP or SL"}), 400

    signal = Signal.query.get_or_404(signal_id)

    if (signal.status or "").upper() != "OPEN":
        return jsonify({"error": "Signal already closed"}), 400

    close_signal_as_result(signal, event_type)

    telegram_results = None
    telegram_error = None

    try:
        if event_type == "TP":
            telegram_results = send_signal_tp(signal)
        else:
            telegram_results = send_signal_sl(signal)

        current_app.logger.info(
            "Manual %s envoyé | trade_id=%s | results=%s",
            event_type,
            signal.trade_id,
            telegram_results,
        )
    except Exception as e:
        telegram_error = str(e)
        current_app.logger.warning(
            "Erreur Telegram %s manual | trade_id=%s | error=%s",
            event_type,
            signal.trade_id,
            e,
        )

    return jsonify({
        "status": "closed",
        "message": f"Signal closed as {event_type}",
        "signal": {
            "id": signal.id,
            "trade_id": signal.trade_id,
            "asset": signal.asset,
            "action": signal.action,
            "status": signal.status,
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "result_percent": signal.result_percent,
            "closed_at": signal.closed_at.isoformat() if getattr(signal, "closed_at", None) else None,
        },
        "telegram_sent": telegram_error is None,
        "telegram_results": telegram_results,
        "telegram_error": telegram_error,
    }), 200