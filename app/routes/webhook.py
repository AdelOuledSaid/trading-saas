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
        current_app.logger.warning("Event non autorisé: %s", event_type)
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
            current_app.logger.warning("Webhook OPEN: données invalides")
            return {"error": "Données invalides"}, 400

        if asset not in config.ALLOWED_ASSETS:
            current_app.logger.warning("Webhook OPEN: actif non autorisé -> %s", asset)
            return {"error": f"Actif non autorisé: {asset}"}, 400

        if action not in config.ALLOWED_ACTIONS:
            current_app.logger.warning("Webhook OPEN: action non autorisée -> %s", action)
            return {"error": f"Action non autorisée: {action}"}, 400

        try:
            sl_distance, tp_distance = get_asset_distances(asset, data)
        except Exception:
            current_app.logger.warning("Webhook OPEN: distances SL/TP invalides")
            return {"error": "Distances SL/TP invalides"}, 400

        if action == "BUY":
            stop_loss = entry_price - sl_distance
            take_profit = entry_price + tp_distance
        else:
            stop_loss = entry_price + sl_distance
            take_profit = entry_price - tp_distance

        if trade_id:
            existing = Signal.query.filter_by(trade_id=trade_id).first()
            if existing:
                current_app.logger.info("Trade déjà existant, ignoré: %s", trade_id)
                return {"status": "ignored", "reason": "trade_id already exists"}, 200

        ai_data = {
            "rsi": _safe_float(data.get("rsi")),
            "trend": str(data.get("trend", "")).strip().lower(),
            "breakout": _safe_bool(data.get("breakout")),
            "volume": _safe_bool(data.get("volume")),
            "adx": _safe_float(data.get("adx")),
            "atr": _safe_float(data.get("atr")),
            "news_sentiment": _safe_float(data.get("news_sentiment")),
        }

        current_app.logger.info("AI DATA = %s", ai_data)

        confidence = compute_confidence(ai_data)
        reason = generate_reason(ai_data)

        current_app.logger.info(
            "AI RESULT = confidence=%s | reason=%s",
            confidence,
            reason
        )

        signal = Signal(
            trade_id=trade_id or None,
            asset=asset,
            action=action,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            status="OPEN",
            timeframe=str(data.get("timeframe", "")).strip() or None,
            signal_type=str(data.get("signal_type", "intraday")).strip() or "intraday",
            market_trend=str(data.get("trend", "")).strip() or None,
            source=str(data.get("source", "tradingview")).strip() or "tradingview",
            news_sentiment=_safe_float(data.get("news_sentiment")),
            confidence=confidence,
            reason=reason,
        )

        if hasattr(signal, "update_risk_reward"):
            signal.update_risk_reward()
        elif hasattr(signal, "compute_rr"):
            signal.risk_reward = signal.compute_rr()

        db.session.add(signal)
        db.session.commit()

        current_app.logger.info(
            "Signal OPEN enregistré | trade_id=%s | asset=%s | action=%s | entry=%s | rr=%s",
            signal.trade_id,
            signal.asset,
            signal.action,
            signal.entry_price,
            getattr(signal, "risk_reward", None),
        )

        try:
            send_telegram_message(build_signal_telegram_message(signal))
            current_app.logger.info("Telegram OPEN envoyé | trade_id=%s", signal.trade_id)
        except Exception as e:
            current_app.logger.warning("Erreur Telegram OPEN: %s", e)

        return {
            "status": "ok",
            "event": "OPEN",
            "trade_id": signal.trade_id,
            "asset": signal.asset,
            "action": signal.action,
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "confidence": signal.confidence,
            "reason": signal.reason,
        }, 200

    # =========================
    # CLOSE SIGNAL
    # =========================
    if event_type in ["TP", "SL"]:
        trade_id = str(data.get("trade_id", "")).strip()
        asset = str(data.get("asset", "")).strip().upper()

        current_app.logger.info(
            "CLOSE EVENT reçu | event=%s | trade_id=%s | asset=%s",
            event_type, trade_id, asset
        )

        signal = find_open_signal_for_closure(trade_id=trade_id, asset=asset)

        if not signal:
            current_app.logger.warning(
                "Aucun signal OPEN trouvé | event=%s | trade_id=%s | asset=%s",
                event_type, trade_id, asset
            )
            return {"error": "Signal introuvable"}, 404

        current_app.logger.info(
            "Signal OPEN trouvé pour fermeture | db_id=%s | trade_id=%s | asset=%s | status=%s",
            signal.id,
            signal.trade_id,
            signal.asset,
            signal.status,
        )

        close_signal_as_result(signal, event_type)

        current_app.logger.info(
            "Signal fermé | trade_id=%s | asset=%s | nouveau_status=%s",
            signal.trade_id,
            signal.asset,
            signal.status,
        )

        try:
            if event_type == "TP":
                send_telegram_message(build_tp_telegram_message(signal))
                current_app.logger.info("Telegram TP envoyé | trade_id=%s", signal.trade_id)
            else:
                send_telegram_message(build_sl_telegram_message(signal))
                current_app.logger.info("Telegram SL envoyé | trade_id=%s", signal.trade_id)
        except Exception as e:
            current_app.logger.warning("Erreur Telegram %s: %s", event_type, e)

        return {
            "status": "closed",
            "event": event_type,
            "trade_id": signal.trade_id,
            "asset": signal.asset,
            "result": signal.status,
        }, 200

    return {"error": "Event inconnu"}, 400


# =========================
# HELPERS
# =========================
def _safe_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_bool(value):
    if isinstance(value, bool):
        return value

    if value is None:
        return False

    if isinstance(value, (int, float)):
        return bool(value)

    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "on"}

    return False