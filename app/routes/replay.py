from datetime import datetime, timedelta, timezone
import random

from flask import Blueprint, render_template, jsonify, abort, request, redirect, url_for, has_request_context
from flask_login import login_required, current_user
from sqlalchemy import func

from app.extensions import db
from app.models import Signal
from app.models.replay import TradeReplay, UserReplayDecision, ReplayCandle
from app.services.replay_recorder_service import ensure_trade_replay_for_signal
from app.services.universal_candles_service import fetch_candles
from app.services.replay_engine_service import build_replay_engine_result


replay_bp = Blueprint("replay", __name__)


# =========================
# MULTI LANG REPLAY
# =========================
SUPPORTED_LANGS = {"fr", "en", "es", "de", "it", "pt", "ru"}

TEXTS = {
    "hold": {"fr": "Conserver", "en": "Hold", "es": "Mantener", "de": "Halten", "it": "Mantenere", "pt": "Manter", "ru": "Держать"},
    "partial": {"fr": "Alléger", "en": "Reduce", "es": "Reducir", "de": "Reduzieren", "it": "Ridurre", "pt": "Reduzir", "ru": "Сократить"},
    "close": {"fr": "Fermer", "en": "Close", "es": "Cerrar", "de": "Schließen", "it": "Chiudere", "pt": "Fechar", "ru": "Закрыть"},

    "good": {"fr": "Excellente décision", "en": "Excellent decision", "es": "Excelente decisión", "de": "Ausgezeichnete Entscheidung", "it": "Decisione eccellente", "pt": "Excelente decisão", "ru": "Отличное решение"},
    "medium": {"fr": "Décision moyenne", "en": "Average decision", "es": "Decisión media", "de": "Durchschnittliche Entscheidung", "it": "Decisione media", "pt": "Decisão média", "ru": "Среднее решение"},
    "bad": {"fr": "Mauvaise décision", "en": "Bad decision", "es": "Mala decisión", "de": "Schlechte Entscheidung", "it": "Decisione sbagliata", "pt": "Má decisão", "ru": "Плохое решение"},
    "decision_analyzed": {"fr": "Décision analysée", "en": "Decision analyzed", "es": "Decisión analizada", "de": "Entscheidung analysiert", "it": "Decisione analizzata", "pt": "Decisão analisada", "ru": "Решение проанализировано"},

    "excellent_choice": {"fr": "Excellente décision", "en": "Excellent decision", "es": "Excelente decisión", "de": "Ausgezeichnete Entscheidung", "it": "Decisione eccellente", "pt": "Excelente decisão", "ru": "Отличное решение"},
    "prudent_management": {"fr": "Gestion prudente", "en": "Prudent management", "es": "Gestión prudente", "de": "Vorsichtiges Management", "it": "Gestione prudente", "pt": "Gestão prudente", "ru": "Осторожное управление"},
    "aggressive_but_valid": {"fr": "Choix défendable mais agressif", "en": "Defensible but aggressive choice", "es": "Elección defendible pero agresiva", "de": "Vertretbare, aber aggressive Entscheidung", "it": "Scelta difendibile ma aggressiva", "pt": "Escolha defensável, mas agressiva", "ru": "Оправданный, но агрессивный выбор"},
    "too_conservative_exit": {"fr": "Sortie trop conservatrice", "en": "Exit too conservative", "es": "Salida demasiado conservadora", "de": "Zu konservativer Ausstieg", "it": "Uscita troppo conservativa", "pt": "Saída conservadora demais", "ru": "Слишком консервативный выход"},
    "limits_damage": {"fr": "Tu limites la casse mais tu restes exposé", "en": "You limit the damage, but you remain exposed", "es": "Limitas el daño, pero sigues expuesto", "de": "Du begrenzt den Schaden, bleibst aber exponiert", "it": "Limiti il danno, ma resti esposto", "pt": "Você limita o dano, mas continua exposto", "ru": "Ты ограничиваешь ущерб, но остаешься под риском"},
    "ignore_invalidation": {"fr": "Tu ignores l’invalidation du setup", "en": "You ignore the setup invalidation", "es": "Ignoras la invalidación del setup", "de": "Du ignorierst die Invalidierung des Setups", "it": "Ignori l’invalidazione del setup", "pt": "Você ignora a invalidação do setup", "ru": "Ты игнорируешь отмену сетапа"},
    "emotional_exit": {"fr": "Sortie émotionnelle sur un setup à fort potentiel", "en": "Emotional exit on a high-potential setup", "es": "Salida emocional en un setup de alto potencial", "de": "Emotionaler Ausstieg bei einem Setup mit hohem Potenzial", "it": "Uscita emotiva su un setup ad alto potenziale", "pt": "Saída emocional em um setup de alto potencial", "ru": "Эмоциональный выход из сетапа с высоким потенциалом"},
    "cut_too_early": {"fr": "Tu coupes trop tôt", "en": "You exit too early", "es": "Sales demasiado pronto", "de": "Du steigst zu früh aus", "it": "Esci troppo presto", "pt": "Você sai cedo demais", "ru": "Ты выходишь слишком рано"},
    "acceptable_not_optimal": {"fr": "Décision acceptable mais non optimale", "en": "Acceptable but not optimal decision", "es": "Decisión aceptable pero no óptima", "de": "Akzeptable, aber nicht optimale Entscheidung", "it": "Decisione accettabile ma non ottimale", "pt": "Decisão aceitável, mas não ideal", "ru": "Приемлемое, но не оптимальное решение"},

    "feedback_hold_good": {"fr": "✅ Très bon choix. Le plan de trade devait être respecté malgré la pression du marché.", "en": "✅ Very good choice. The trade plan had to be respected despite market pressure.", "es": "✅ Muy buena elección. El plan debía respetarse pese a la presión del mercado.", "de": "✅ Sehr gute Wahl. Der Trading-Plan musste trotz Marktdruck respektiert werden.", "it": "✅ Ottima scelta. Il piano di trading andava rispettato nonostante la pressione del mercato.", "pt": "✅ Muito boa escolha. O plano precisava ser respeitado apesar da pressão do mercado.", "ru": "✅ Очень хороший выбор. План сделки нужно было соблюдать несмотря на давление рынка."},
    "feedback_partial_good": {"fr": "✅ Bonne lecture. Sécuriser partiellement était la meilleure réponse dans ce contexte.", "en": "✅ Good read. Partial protection was the best response in this context.", "es": "✅ Buena lectura. Asegurar parcialmente era la mejor respuesta en este contexto.", "de": "✅ Gute Einschätzung. Teilweises Absichern war hier die beste Reaktion.", "it": "✅ Buona lettura. Proteggere parzialmente era la risposta migliore in questo contesto.", "pt": "✅ Boa leitura. Proteger parcialmente era a melhor resposta neste contexto.", "ru": "✅ Хорошее чтение рынка. Частичная фиксация была лучшим решением в этом контексте."},
    "feedback_close_good": {"fr": "✅ Bonne décision. Le setup était invalidé, sortir protégeait le capital.", "en": "✅ Good decision. The setup was invalidated, exiting protected capital.", "es": "✅ Buena decisión. El setup estaba invalidado, salir protegía el capital.", "de": "✅ Gute Entscheidung. Das Setup war invalidiert, Ausstieg schützte Kapital.", "it": "✅ Buona decisione. Il setup era invalidato, uscire proteggeva il capitale.", "pt": "✅ Boa decisão. O setup foi invalidado, sair protegeu o capital.", "ru": "✅ Хорошее решение. Сетап был отменен, выход защитил капитал."},
    "feedback_should_hold": {"fr": "⚠️ Le setup n’était pas encore invalidé. Un trader discipliné laissait davantage respirer la position.", "en": "⚠️ The setup was not invalidated yet. A disciplined trader would have allowed the position more room.", "es": "⚠️ El setup aún no estaba invalidado. Un trader disciplinado habría dejado respirar más la posición.", "de": "⚠️ Das Setup war noch nicht invalidiert. Ein disziplinierter Trader hätte der Position mehr Raum gegeben.", "it": "⚠️ Il setup non era ancora invalidato. Un trader disciplinato avrebbe lasciato più spazio alla posizione.", "pt": "⚠️ O setup ainda não estava invalidado. Um trader disciplinado deixaria a posição respirar mais.", "ru": "⚠️ Сетап еще не был отменен. Дисциплинированный трейдер дал бы позиции больше пространства."},
    "feedback_should_partial": {"fr": "⚠️ Le contexte appelait une gestion intermédiaire. Tout couper ou tout laisser courir n’était pas optimal.", "en": "⚠️ The context called for intermediate management. Fully closing or fully holding was not optimal.", "es": "⚠️ El contexto pedía una gestión intermedia. Cerrar todo o dejar todo correr no era óptimo.", "de": "⚠️ Der Kontext verlangte ein Zwischenmanagement. Alles schließen oder alles laufen lassen war nicht optimal.", "it": "⚠️ Il contesto richiedeva una gestione intermedia. Chiudere tutto o lasciare correre tutto non era ottimale.", "pt": "⚠️ O contexto pedia uma gestão intermediária. Fechar tudo ou deixar tudo correr não era ideal.", "ru": "⚠️ Контекст требовал промежуточного управления. Полностью закрывать или полностью держать было не оптимально."},
    "feedback_should_close": {"fr": "❌ Le marché ne validait plus le scénario initial. Il fallait réduire fortement le risque ou sortir.", "en": "❌ The market no longer validated the initial scenario. Risk had to be strongly reduced or the trade closed.", "es": "❌ El mercado ya no validaba el escenario inicial. Había que reducir mucho el riesgo o salir.", "de": "❌ Der Markt bestätigte das ursprüngliche Szenario nicht mehr. Das Risiko musste stark reduziert oder der Trade geschlossen werden.", "it": "❌ Il mercato non validava più lo scenario iniziale. Bisognava ridurre fortemente il rischio o uscire.", "pt": "❌ O mercado já não validava o cenário inicial. Era preciso reduzir fortemente o risco ou sair.", "ru": "❌ Рынок больше не подтверждал первоначальный сценарий. Нужно было сильно снизить риск или выйти."},

    "structure_detected": {"fr": "Structure détectée : {value}.", "en": "Detected structure: {value}.", "es": "Estructura detectada: {value}.", "de": "Erkannte Struktur: {value}.", "it": "Struttura rilevata: {value}.", "pt": "Estrutura detectada: {value}.", "ru": "Обнаруженная структура: {value}."},
    "htf_bias": {"fr": "Biais HTF : {value}.", "en": "HTF bias: {value}.", "es": "Sesgo HTF: {value}.", "de": "HTF-Bias: {value}.", "it": "Bias HTF: {value}.", "pt": "Viés HTF: {value}.", "ru": "HTF bias: {value}."},
    "trade_state": {"fr": "État du trade au moment de décision : {value}.", "en": "Trade state at decision moment: {value}.", "es": "Estado de la operación en el momento de decisión: {value}.", "de": "Trade-Zustand im Entscheidungsmoment: {value}.", "it": "Stato del trade al momento decisionale: {value}.", "pt": "Estado do trade no momento da decisão: {value}.", "ru": "Состояние сделки в момент решения: {value}."},

    "replay_not_found": {"fr": "Replay introuvable", "en": "Replay not found", "es": "Replay no encontrado", "de": "Replay nicht gefunden", "it": "Replay non trovato", "pt": "Replay não encontrado", "ru": "Replay не найден"},
    "invalid_decision": {"fr": "Décision invalide", "en": "Invalid decision", "es": "Decisión inválida", "de": "Ungültige Entscheidung", "it": "Decisione non valida", "pt": "Decisão inválida", "ru": "Недопустимое решение"},
    "decision_saved": {"fr": "Décision sauvegardée", "en": "Decision saved", "es": "Decisión guardada", "de": "Entscheidung gespeichert", "it": "Decisione salvata", "pt": "Decisão salva", "ru": "Решение сохранено"},
    "save_error": {"fr": "Erreur sauvegarde", "en": "Save error", "es": "Error al guardar", "de": "Speicherfehler", "it": "Errore di salvataggio", "pt": "Erro ao salvar", "ru": "Ошибка сохранения"},
    "replay_data_error": {"fr": "Erreur données replay: {error}", "en": "Replay data error: {error}", "es": "Error de datos replay: {error}", "de": "Replay-Datenfehler: {error}", "it": "Errore dati replay: {error}", "pt": "Erro nos dados do replay: {error}", "ru": "Ошибка данных replay: {error}"},
    "no_replay_data": {"fr": "Aucune donnée replay disponible", "en": "No replay data available", "es": "No hay datos replay disponibles", "de": "Keine Replay-Daten verfügbar", "it": "Nessun dato replay disponibile", "pt": "Nenhum dado de replay disponível", "ru": "Нет доступных данных replay"},
    "no_candle_build": {"fr": "Impossible de construire le replay: aucune bougie exploitable.", "en": "Unable to build replay: no usable candle data.", "es": "No se puede construir el replay: no hay velas utilizables.", "de": "Replay kann nicht erstellt werden: keine nutzbaren Kerzendaten.", "it": "Impossibile costruire il replay: nessuna candela utilizzabile.", "pt": "Não foi possível construir o replay: nenhum candle utilizável.", "ru": "Невозможно построить replay: нет пригодных свечей."},
    "desk_note": {"fr": "Ce replay utilise un scénario auto-guidé stable avec une décision manuelle au moment critique.", "en": "This replay uses a stable auto-guided scenario with a manual decision at the critical moment.", "es": "Este replay usa un escenario auto-guiado estable con decisión manual en el momento crítico.", "de": "Dieses Replay nutzt ein stabiles automatisch geführtes Szenario mit manueller Entscheidung im kritischen Moment.", "it": "Questo replay usa uno scenario auto-guidato stabile con decisione manuale nel momento critico.", "pt": "Este replay usa um cenário auto-guiado estável com decisão manual no momento crítico.", "ru": "Этот replay использует стабильный авто-сценарий с ручным решением в критический момент."},
    "comparison_text": {"fr": "Tu fais mieux que {value}% des traders sur cette décision.", "en": "You performed better than {value}% of traders on this decision.", "es": "Lo hiciste mejor que el {value}% de los traders en esta decisión.", "de": "Du warst bei dieser Entscheidung besser als {value}% der Trader.", "it": "Hai fatto meglio del {value}% dei trader su questa decisione.", "pt": "Você teve desempenho melhor que {value}% dos traders nesta decisão.", "ru": "Ты справился лучше, чем {value}% трейдеров в этом решении."},
}


def _lang():
    if has_request_context():
        lang = request.args.get("lang_code") or (request.view_args or {}).get("lang_code") or "en"
    else:
        lang = "en"

    lang = str(lang or "en").lower()
    return lang if lang in SUPPORTED_LANGS else "en"


def tr(key, **kwargs):
    value = TEXTS.get(key, {}).get(_lang()) or TEXTS.get(key, {}).get("en") or key
    try:
        return value.format(**kwargs)
    except Exception:
        return value


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
        "hold": tr("hold"),
        "partial": tr("partial"),
        "close": tr("close"),
    }
    return mapping.get(decision, decision)


def _score_decision(choice, ideal_decision, result, rr):
    rr = _safe_float(rr, 1.0)
    result = (result or "").upper()

    if choice == ideal_decision:
        return 10, "good", tr("excellent_choice")

    if ideal_decision == "hold" and choice == "partial":
        return 6, "medium", tr("prudent_management")

    if ideal_decision == "partial" and choice == "hold":
        return 5, "medium", tr("aggressive_but_valid")

    if ideal_decision == "partial" and choice == "close":
        return 3, "bad", tr("too_conservative_exit")

    if ideal_decision == "close" and choice == "partial":
        return 4, "medium", tr("limits_damage")

    if ideal_decision == "close" and choice == "hold":
        return 0, "bad", tr("ignore_invalidation")

    if ideal_decision == "hold" and choice == "close":
        if rr >= 2:
            return 1, "bad", tr("emotional_exit")
        return 2, "bad", tr("cut_too_early")

    return 4, "medium", tr("acceptable_not_optimal")


def _feedback_message(choice, ideal_decision, result):
    if choice == ideal_decision:
        if choice == "hold":
            return tr("feedback_hold_good")
        if choice == "partial":
            return tr("feedback_partial_good")
        return tr("feedback_close_good")

    if ideal_decision == "hold":
        return tr("feedback_should_hold")
    if ideal_decision == "partial":
        return tr("feedback_should_partial")
    return tr("feedback_should_close")


def _status_label(status):
    status = (status or "").lower()
    mapping = {
        "good": tr("good"),
        "medium": tr("medium"),
        "bad": tr("bad"),
    }
    return mapping.get(status, tr("decision_analyzed"))


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


def _parse_dt(value):
    if not value:
        return None

    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(raw)
        except Exception:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt


def _clean_candles(candles):
    cleaned = []
    seen = set()
    sortable = []

    for candle in candles or []:
        dt = _parse_dt(candle.get("time"))
        if dt is None:
            continue

        open_p = _safe_float(candle.get("open"), None)
        high_p = _safe_float(candle.get("high"), None)
        low_p = _safe_float(candle.get("low"), None)
        close_p = _safe_float(candle.get("close"), None)

        if None in [open_p, high_p, low_p, close_p]:
            continue

        sortable.append(
            (
                dt,
                {
                    "time": dt.isoformat(),
                    "open": open_p,
                    "high": max(high_p, open_p, close_p, low_p),
                    "low": min(low_p, open_p, close_p, high_p),
                    "close": close_p,
                    "volume": _safe_float(candle.get("volume"), None),
                },
            )
        )

    sortable.sort(key=lambda x: x[0])

    for _, candle in sortable:
        if candle["time"] in seen:
            continue
        seen.add(candle["time"])
        candle["index"] = len(cleaned)
        cleaned.append(candle)

    return cleaned


def _normalize_candles(raw_candles):
    normalized = []
    for candle in raw_candles or []:
        normalized.append(
            {
                "time": candle.get("time"),
                "open": _safe_float(candle.get("open"), None),
                "high": _safe_float(candle.get("high"), None),
                "low": _safe_float(candle.get("low"), None),
                "close": _safe_float(candle.get("close"), None),
                "volume": _safe_float(candle.get("volume"), None)
                if candle.get("volume") is not None
                else None,
            }
        )
    return _clean_candles(normalized)


def _find_index_by_time(candles, target_time):
    if not candles or not target_time:
        return 0

    target_dt = _parse_dt(target_time)
    if target_dt is None:
        return 0

    target_ts = target_dt.timestamp()
    best_idx = 0
    best_diff = None

    for candle in candles:
        candle_dt = _parse_dt(candle.get("time"))
        if candle_dt is None:
            continue

        diff = abs(candle_dt.timestamp() - target_ts)
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_idx = candle["index"]

    return best_idx


def _trim_centered_on_entry(candles, entry_time, max_count=180, pre_bars=40):
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

    return [
        {
            "label": "HTF Supply",
            "low": round(recent_high - zone_size, 6),
            "high": round(recent_high, 6),
        },
        {
            "label": "HTF Demand",
            "low": round(recent_low, 6),
            "high": round(recent_low + zone_size, 6),
        },
    ]


def _build_lessons_from_engine(engine):
    lessons = [
        tr("structure_detected", value=engine.market_structure),
        tr("htf_bias", value=engine.htf_bias),
        tr("trade_state", value=engine.trade_health),
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

    start_dt = entry_dt - timedelta(hours=16)
    end_dt = replay_end + timedelta(hours=16)

    return start_dt, end_dt


def _stored_candles_for_replay(replay):
    rows = (
        ReplayCandle.query.filter_by(trade_replay_id=replay.id)
        .order_by(ReplayCandle.position_index.asc(), ReplayCandle.candle_time.asc())
        .all()
    )

    candles = []
    for row in rows:
        candles.append(
            {
                "time": row.candle_time.isoformat() if row.candle_time else None,
                "open": _safe_float(row.open, None),
                "high": _safe_float(row.high, None),
                "low": _safe_float(row.low, None),
                "close": _safe_float(row.close, None),
                "volume": _safe_float(row.volume, None),
            }
        )

    return _clean_candles(candles)


def _timeframe_to_minutes(timeframe):
    tf = (timeframe or "15m").lower()
    mapping = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "4h": 240,
        "1d": 1440,
    }
    return mapping.get(tf, 15)


def _generate_fallback_candles_for_replay(
    replay,
    timeframe="15m",
    count=120,
    pre_bars=40,
):
    entry_price = _safe_float(replay.entry_price, 0.0)
    stop_loss = _safe_float(replay.stop_loss, entry_price * 0.998 if entry_price else 0.0)
    take_profit = _safe_float(replay.take_profit, entry_price * 1.002 if entry_price else 0.0)

    if entry_price <= 0:
        return []

    direction = (replay.direction or "BUY").upper()
    result = (replay.result or "OPEN").upper()

    minutes = _timeframe_to_minutes(timeframe)
    step = timedelta(minutes=minutes)

    entry_dt = replay.entry_time or replay.replay_start or datetime.now(timezone.utc)
    if entry_dt.tzinfo is None:
        entry_dt = entry_dt.replace(tzinfo=timezone.utc)

    start_dt = entry_dt - (step * pre_bars)
    rng = random.Random(f"{replay.id}-{replay.symbol}-{timeframe}")

    candles = []
    price = entry_price * (0.999 if direction == "BUY" else 1.001)

    if direction == "BUY":
        if result == "WIN":
            exit_target = take_profit
        elif result == "LOSS":
            exit_target = stop_loss
        else:
            exit_target = entry_price + ((take_profit - entry_price) * 0.35)
    else:
        if result == "WIN":
            exit_target = take_profit
        elif result == "LOSS":
            exit_target = stop_loss
        else:
            exit_target = entry_price - ((entry_price - take_profit) * 0.35)

    for i in range(count):
        current_time = start_dt + (step * i)

        if i < pre_bars:
            drift = (entry_price - price) * 0.18
        else:
            progress = (i - pre_bars) / max(1, (count - pre_bars - 1))
            desired = entry_price + (exit_target - entry_price) * progress
            drift = (desired - price) * 0.22

        noise = entry_price * rng.uniform(-0.00045, 0.00045)
        body_move = drift + noise

        open_p = price
        close_p = max(0.0001, open_p + body_move)

        wick_up = abs(entry_price * rng.uniform(0.00008, 0.00035))
        wick_down = abs(entry_price * rng.uniform(0.00008, 0.00035))

        high_p = max(open_p, close_p) + wick_up
        low_p = min(open_p, close_p) - wick_down

        if i == pre_bars:
            open_p = entry_price * (0.9997 if direction == "BUY" else 1.0003)
            close_p = entry_price
            high_p = max(open_p, close_p) + wick_up
            low_p = min(open_p, close_p) - wick_down

        candles.append(
            {
                "time": current_time.isoformat(),
                "open": round(open_p, 6),
                "high": round(high_p, 6),
                "low": round(low_p, 6),
                "close": round(close_p, 6),
                "volume": round(rng.uniform(10, 150), 2),
            }
        )

        price = close_p

    if candles:
        if direction == "BUY":
            candles[-1]["close"] = round(exit_target, 6)
            candles[-1]["high"] = round(max(candles[-1]["high"], exit_target), 6)
            candles[-1]["low"] = round(min(candles[-1]["low"], candles[-1]["open"], candles[-1]["close"]), 6)
        else:
            candles[-1]["close"] = round(exit_target, 6)
            candles[-1]["low"] = round(min(candles[-1]["low"], exit_target), 6)
            candles[-1]["high"] = round(max(candles[-1]["high"], candles[-1]["open"], candles[-1]["close"]), 6)

    return _clean_candles(candles)


def _generate_fallback_htf_candles(replay, higher_tf="1h", count=80):
    entry_price = _safe_float(replay.entry_price, 0.0)
    if entry_price <= 0:
        return []

    direction = (replay.direction or "BUY").upper()
    minutes = _timeframe_to_minutes(higher_tf)
    step = timedelta(minutes=minutes)

    anchor_dt = replay.entry_time or replay.replay_start or datetime.now(timezone.utc)
    if anchor_dt.tzinfo is None:
        anchor_dt = anchor_dt.replace(tzinfo=timezone.utc)

    start_dt = anchor_dt - (step * (count // 2))
    rng = random.Random(f"htf-{replay.id}-{replay.symbol}-{higher_tf}")

    candles = []
    price = entry_price * (0.992 if direction == "BUY" else 1.008)
    trend_sign = 1 if direction == "BUY" else -1

    for i in range(count):
        current_time = start_dt + (step * i)
        drift = entry_price * trend_sign * 0.0009
        noise = entry_price * rng.uniform(-0.0006, 0.0006)

        open_p = price
        close_p = max(0.0001, open_p + drift + noise)
        high_p = max(open_p, close_p) + abs(entry_price * rng.uniform(0.0002, 0.0007))
        low_p = min(open_p, close_p) - abs(entry_price * rng.uniform(0.0002, 0.0007))

        candles.append(
            {
                "time": current_time.isoformat(),
                "open": round(open_p, 6),
                "high": round(high_p, 6),
                "low": round(low_p, 6),
                "close": round(close_p, 6),
                "volume": round(rng.uniform(50, 300), 2),
            }
        )

        price = close_p

    return _clean_candles(candles)


def _load_primary_candles_for_replay(replay, timeframe):
    start_dt, end_dt = _history_window_for_replay(replay)

    stored_candles = _stored_candles_for_replay(replay)
    stored_trimmed = _trim_centered_on_entry(
        stored_candles,
        entry_time=replay.entry_time,
        max_count=180,
        pre_bars=40,
    )

    market_raw = []
    market_candles = []
    market_error = None

    try:
        market_raw = fetch_candles(
            asset=replay.symbol,
            timeframe=timeframe,
            limit=1000,
            start_time=start_dt,
            end_time=end_dt,
        )

        market_candles = _trim_centered_on_entry(
            _normalize_candles(market_raw),
            entry_time=replay.entry_time,
            max_count=180,
            pre_bars=40,
        )
    except Exception as exc:
        market_error = str(exc)

    source = "market"
    final_raw = market_raw
    final_candles = market_candles

    if stored_trimmed and (not market_candles or len(stored_trimmed) >= len(market_candles)):
        source = "stored"
        final_raw = stored_candles
        final_candles = stored_trimmed

    if not final_candles and stored_trimmed:
        source = "stored"
        final_raw = stored_candles
        final_candles = stored_trimmed

    if not final_candles:
        fallback_candles = _generate_fallback_candles_for_replay(
            replay=replay,
            timeframe=timeframe,
            count=140,
            pre_bars=40,
        )
        source = "fallback"
        final_raw = fallback_candles
        final_candles = fallback_candles
        market_raw = fallback_candles

    debug = {
        "source": source,
        "stored_len": len(stored_candles),
        "stored_trimmed_len": len(stored_trimmed),
        "market_len": len(market_candles),
        "market_raw_len": len(market_raw or []),
        "market_error": market_error,
    }

    return final_raw, final_candles, start_dt, end_dt, debug


def _load_htf_candles_for_replay(replay, higher_tf):
    start_dt, end_dt = _history_window_for_replay(replay)

    try:
        raw = fetch_candles(
            asset=replay.symbol,
            timeframe=higher_tf,
            limit=400,
            start_time=start_dt - timedelta(hours=24),
            end_time=end_dt + timedelta(hours=24),
        )

        cleaned = _normalize_candles(raw)
        if cleaned:
            return cleaned
    except Exception:
        pass

    return _generate_fallback_htf_candles(
        replay=replay,
        higher_tf=higher_tf,
        count=80,
    )


# =========================
# ROUTES
# =========================
@replay_bp.route("/signal/<int:signal_id>/replay")
@replay_bp.route("/<lang_code>/signal/<int:signal_id>/replay")
@login_required
def open_signal_replay(signal_id, lang_code="fr"):
    signal = Signal.query.filter_by(id=signal_id, is_deleted=False).first_or_404()
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
    replay = (
        TradeReplay.query
        .join(Signal, TradeReplay.signal_id == Signal.id)
        .filter(
            TradeReplay.id == replay_id,
            Signal.is_deleted == False
        )
        .first()
    )

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
    replay = (
        TradeReplay.query
        .join(Signal, TradeReplay.signal_id == Signal.id)
        .filter(
            TradeReplay.id == replay_id,
            Signal.is_deleted == False
        )
        .first()
    )

    if not replay:
        return jsonify({"error": tr("replay_not_found")}), 404

    primary_tf = (replay.timeframe or "15m").lower()
    higher_tf = _next_higher_timeframe(primary_tf)

    try:
        primary_raw, primary_candles, start_dt, end_dt, primary_debug = _load_primary_candles_for_replay(
            replay, primary_tf
        )
    except Exception as e:
        return jsonify({"error": tr("replay_data_error", error=str(e))}), 500

    try:
        htf_candles = _load_htf_candles_for_replay(replay, higher_tf)
        htf_error = None
    except Exception as e:
        htf_candles = []
        htf_error = str(e)

    if primary_raw is None or not isinstance(primary_raw, list) or len(primary_raw) == 0:
        return (
            jsonify(
                {
                    "error": tr("no_replay_data"),
                    "debug": {
                        "symbol": replay.symbol,
                        "timeframe": primary_tf,
                        **primary_debug,
                    },
                }
            ),
            404,
        )

    if not primary_candles:
        return (
            jsonify(
                {
                    "error": tr("no_candle_build"),
                    "debug": {
                        "symbol": replay.symbol,
                        "timeframe": primary_tf,
                        "window_start": start_dt.isoformat(),
                        "window_end": end_dt.isoformat(),
                        **primary_debug,
                    },
                }
            ),
            400,
        )

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

    rr_value = _compute_rr(replay.entry_price, replay.stop_loss, replay.take_profit)
    confidence_value = getattr(replay, "confidence", 0) or 0
    risk_reward_value = getattr(replay, "risk_reward", None) or rr_value or 0
    setup_grade = _compute_setup_grade(confidence_value, risk_reward_value)
    difficulty = _compute_difficulty(confidence_value, risk_reward_value, len(engine.events))
    ideal_decision = _ideal_decision_from_result(engine.derived_result)
    htf_zones = _build_htf_zones(htf_candles)
    lessons = _build_lessons_from_engine(engine)

    return jsonify(
        {
            "trade": {
                "id": replay.id,
                "signal_id": replay.signal_id,
                "symbol": replay.symbol,
                "timeframe": primary_tf,
                "higher_timeframe": higher_tf,
                "direction": replay.direction,
                "simulation_mode": "auto_guided",
                "decision_mode": "manual_decision_only",
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
                "timeline": engine.timeline,
                "user_hint_before_decision": engine.decision_context,
                "desk_note": tr("desk_note"),
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
                "first_candle_time": primary_candles[0]["time"] if primary_candles else None,
                "last_candle_time": primary_candles[-1]["time"] if primary_candles else None,
                "entry_time": replay.entry_time.isoformat() if replay.entry_time else None,
                "htf_error": htf_error,
                **primary_debug,
            },
            "candles": primary_candles,
            "higher_timeframe_candles": htf_candles,
            "events": engine.events,
        }
    )


@replay_bp.route("/api/replay/<int:replay_id>/decision", methods=["POST"])
@replay_bp.route("/<lang_code>/api/replay/<int:replay_id>/decision", methods=["POST"])
@login_required
def save_replay_decision(replay_id, lang_code="fr"):
    replay = (
        TradeReplay.query
        .join(Signal, TradeReplay.signal_id == Signal.id)
        .filter(
            TradeReplay.id == replay_id,
            Signal.is_deleted == False
        )
        .first()
    )

    if not replay:
        return jsonify({"error": tr("replay_not_found")}), 404

    data = request.get_json() or {}
    decision = (data.get("decision") or "").strip().lower()

    if decision not in ["close", "hold", "partial"]:
        return jsonify({"error": tr("invalid_decision")}), 400

    existing = (
        UserReplayDecision.query.filter_by(
            user_id=current_user.id,
            trade_replay_id=replay.id,
        )
        .order_by(UserReplayDecision.created_at.desc())
        .first()
    )

    primary_tf = (replay.timeframe or "15m").lower()
    higher_tf = _next_higher_timeframe(primary_tf)

    try:
        _, primary_candles, _, _, _ = _load_primary_candles_for_replay(replay, primary_tf)
    except Exception as e:
        return jsonify({"error": tr("replay_data_error", error=str(e))}), 500

    try:
        htf_candles = _load_htf_candles_for_replay(replay, higher_tf)
    except Exception:
        htf_candles = []

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

    rr_value = _compute_rr(replay.entry_price, replay.stop_loss, replay.take_profit) or getattr(
        replay, "risk_reward", 1
    )
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
            db.session.add(
                UserReplayDecision(
                    user_id=current_user.id,
                    trade_replay_id=replay.id,
                    decision=decision,
                    score=int(score),
                    status=status,
                    feedback=feedback,
                )
            )

        db.session.commit()

        user_avg_score = db.session.query(func.avg(UserReplayDecision.score)).filter(
            UserReplayDecision.user_id == current_user.id
        ).scalar()
        user_avg_score = round(float(user_avg_score), 1) if user_avg_score is not None else 0.0
        estimated_percentile = min(99, max(1, int((score / 10) * 100) - 8))

        return (
            jsonify(
                {
                    "success": True,
                    "message": tr("decision_saved"),
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
                    "comparison_text": tr("comparison_text", value=estimated_percentile),
                }
            ),
            201,
        )
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": tr("save_error"), "details": str(e)}), 500


@replay_bp.route("/my-performance")
@replay_bp.route("/<lang_code>/my-performance")
@login_required
def my_performance(lang_code="fr"):
    base_query = (
        db.session.query(UserReplayDecision)
        .join(TradeReplay, UserReplayDecision.trade_replay_id == TradeReplay.id)
        .join(Signal, TradeReplay.signal_id == Signal.id)
        .filter(
            UserReplayDecision.user_id == current_user.id,
            Signal.is_deleted == False
        )
    )

    decisions = (
        base_query
        .order_by(UserReplayDecision.created_at.desc())
        .all()
    )

    total_decisions = len(decisions)

    avg_score = (
        db.session.query(func.avg(UserReplayDecision.score))
        .join(TradeReplay, UserReplayDecision.trade_replay_id == TradeReplay.id)
        .join(Signal, TradeReplay.signal_id == Signal.id)
        .filter(
            UserReplayDecision.user_id == current_user.id,
            Signal.is_deleted == False
        )
        .scalar()
    )
    avg_score = round(float(avg_score), 1) if avg_score is not None else 0

    good_count = (
        db.session.query(UserReplayDecision)
        .join(TradeReplay, UserReplayDecision.trade_replay_id == TradeReplay.id)
        .join(Signal, TradeReplay.signal_id == Signal.id)
        .filter(
            UserReplayDecision.user_id == current_user.id,
            UserReplayDecision.status == "good",
            Signal.is_deleted == False
        )
        .count()
    )

    medium_count = (
        db.session.query(UserReplayDecision)
        .join(TradeReplay, UserReplayDecision.trade_replay_id == TradeReplay.id)
        .join(Signal, TradeReplay.signal_id == Signal.id)
        .filter(
            UserReplayDecision.user_id == current_user.id,
            UserReplayDecision.status == "medium",
            Signal.is_deleted == False
        )
        .count()
    )

    bad_count = (
        db.session.query(UserReplayDecision)
        .join(TradeReplay, UserReplayDecision.trade_replay_id == TradeReplay.id)
        .join(Signal, TradeReplay.signal_id == Signal.id)
        .filter(
            UserReplayDecision.user_id == current_user.id,
            UserReplayDecision.status == "bad",
            Signal.is_deleted == False
        )
        .count()
    )

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