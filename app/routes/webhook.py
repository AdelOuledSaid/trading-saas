from flask import Blueprint, request, current_app

import config
from app.extensions import db
from app.models import Signal
from app.services.signal_service import (
    get_asset_distances,
    close_signal_as_result,
    find_open_signal_for_closure,
)
from app.services.ai_signal_service import compute_confidence, generate_reason
from app.services.telegram_service import (
    send_telegram_message,
    build_signal_telegram_message,
    build_tp_telegram_message,
    build_sl_telegram_message,
)

webhook_bp = Blueprint("webhook", __name__)


@webhook_bp.route("/webhook", methods=["POST"])
def webhook():
    raw_body = request.get_data(as_text=True).strip()
    data = request.get_json(silent=True)

    if not data:
        current_app.logger.info("Webhook ignoré (non JSON): %s", raw_body)
        return {"status": "ignored"}, 200

    current_app.logger.info("Webhook reçu: %s", data)

    # =========================
    # SECURITY
    # =========================
    if config.TRADINGVIEW_WEBHOOK_SECRET and data.get("secret") != config.TRADINGVIEW_WEBHOOK_SECRET:
        current_app.logger.warning("Secret invalide")
        return {"error": "Non autorisé"}, 403

    event_type = str(data.get("event", "OPEN")).strip().upper()

    if event_type not in config.ALLOWED_EVENTS:
        return {"error": f"Event non autorisé: {event_type}"}, 400

    # =========================
    # OPEN SIGNAL
    # =========================
    if event_type == "OPEN":
        try:
            trade_id = str(data.get("trade_id", "")).strip()
            asset = str(data.get("asset", "")).strip().upper()
            action = str(data.get("action", "")).strip().upper()
            entry_price = float(data.get("entry_price"))
        except Exception:
            return {"error": "Données invalides"}, 400

        sl_distance, tp_distance = get_asset_distances(asset, data)

        if action == "BUY":
            stop_loss = entry_price - sl_distance
            take_profit = entry_price + tp_distance
        else:
            stop_loss = entry_price + sl_distance
            take_profit = entry_price - tp_distance

        # éviter doublons
        if trade_id:
            existing = Signal.query.filter_by(trade_id=trade_id).first()
            if existing:
                return {"status": "ignored"}, 200

        # =========================
        # AI DATA (IMPORTANT)
        # =========================
        ai_data = {
            "rsi": _safe_float(data.get("rsi")),
            "trend": str(data.get("trend", "")).strip().lower(),
            "breakout": _safe_bool(data.get("breakout")),
            "volume": _safe_bool(data.get("volume")),
            "adx": _safe_float(data.get("adx")),
            "atr": _safe_float(data.get("atr")),
        }

        current_app.logger.info("AI DATA = %s", ai_data)

        confidence = compute_confidence(ai_data)
        reason = generate_reason(ai_data)

        current_app.logger.info(
            "AI RESULT → confidence=%s reason=%s",
            confidence,
            reason
        )

        # =========================
        # CREATE SIGNAL
        # =========================
        signal = Signal(
            trade_id=trade_id or None,
            asset=asset,
            action=action,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            status="OPEN",
            timeframe=str(data.get("timeframe", "")).strip() or None,
            signal_type=str(data.get("signal_type", "intraday")).strip(),
            market_trend=str(data.get("trend", "")).strip(),
            confidence=confidence,
            reason=reason,
        )

        db.session.add(signal)
        db.session.commit()

        # =========================
        # TELEGRAM
        # =========================
        try:
            send_telegram_message(build_signal_telegram_message(signal))
        except Exception as e:
            current_app.logger.warning("Erreur Telegram: %s", e)

        return {
            "status": "ok",
            "confidence": confidence,
            "reason": reason,
        }, 200

    # =========================
    # CLOSE SIGNAL
    # =========================
    if event_type in ["TP", "SL"]:
        trade_id = str(data.get("trade_id", "")).strip()
        asset = str(data.get("asset", "")).strip().upper()

        signal = find_open_signal_for_closure(trade_id, asset)

        if not signal:
            return {"error": "Signal introuvable"}, 404

        close_signal_as_result(signal, event_type)

        try:
            if event_type == "TP":
                send_telegram_message(build_tp_telegram_message(signal))
            else:
                send_telegram_message(build_sl_telegram_message(signal))
        except Exception:
            pass

        return {"status": "closed"}, 200

    return {"error": "Event inconnu"}, 400


# =========================
# HELPERS
# =========================
def _safe_float(value, default=None):
    try:
        return float(value)
    except:
        return default


def _safe_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ["true", "1"]
    return False