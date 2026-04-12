import hashlib
from datetime import datetime
from datetime import timedelta
from app.extensions import db
from app.models.telegram_dispatch_log import TelegramDispatchLog


def normalize_text(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def hash_text(text: str) -> str:
    normalized = normalize_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def build_article_fingerprint(article: dict) -> str:
    title = normalize_text(str(article.get("title", "")))
    description = normalize_text(str(article.get("description", "")))
    source = normalize_text(str(article.get("source", "")))
    content = f"{title}||{description}||{source}"
    return hash_text(content)


def dispatch_exists(dedup_key: str) -> bool:
    if not dedup_key:
        return False

    existing = TelegramDispatchLog.query.filter_by(dedup_key=dedup_key).first()
    return existing is not None


def dispatch_exists_by_hash(content_type: str, tier: str, content_hash: str) -> bool:
    if not content_hash:
        return False

    existing = TelegramDispatchLog.query.filter_by(
        content_type=content_type,
        tier=tier,
        content_hash=content_hash,
        status="sent",
    ).first()
    return existing is not None


def record_dispatch(
    *,
    content_type: str,
    tier: str,
    dedup_key: str,
    content_text: str | None = None,
    content_ref: str | None = None,
    content_hash: str | None = None,
    status: str = "sent",
) -> TelegramDispatchLog:
    log = TelegramDispatchLog(
        content_type=content_type,
        tier=tier,
        dedup_key=dedup_key,
        content_hash=content_hash or (hash_text(content_text or "") if content_text else None),
        content_ref=content_ref,
        sent_at=datetime.utcnow(),
        status=status,
    )
    db.session.add(log)
    db.session.commit()
    return log


def signal_event_key(event_type: str, tier: str, signal_id: int | None, trade_id: str | None) -> str:
    signal_part = str(signal_id or "none")
    trade_part = str(trade_id or "none")
    return f"{event_type}:{tier}:signal={signal_part}:trade={trade_part}"


def news_digest_key(tier: str, digest_date: str, slot: str, version: str = "v1") -> str:
    return f"daily_news:{tier}:{digest_date}:{slot}:{version}"


def briefing_key(briefing_type: str, tier: str, briefing_date: str, slot: str, version: str = "v1") -> str:
    return f"{briefing_type}:{tier}:{briefing_date}:{slot}:{version}"


def breaking_news_key(tier: str, article_id: str | None = None, article_url: str | None = None) -> str:
    ref = article_id or article_url or "unknown"
    return f"breaking_news:{tier}:{ref}"


def purge_old_dispatch_logs(days: int = 30) -> int:
    """
    Supprime les logs anciens.
    Retourne le nombre de lignes supprimées.
    """
    from datetime import timedelta

    cutoff = datetime.utcnow() - timedelta(days=days)

    old_logs = TelegramDispatchLog.query.filter(
        TelegramDispatchLog.sent_at < cutoff
    ).all()

    count = len(old_logs)

    for log in old_logs:
        db.session.delete(log)

    db.session.commit()
    return count



def count_sent_today(content_type: str, tier: str) -> int:
    """
    Compte combien de messages d’un type ont été envoyés aujourd’hui
    pour un tier donné (ex: signal_open, basic)
    """
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)

    return TelegramDispatchLog.query.filter(
        TelegramDispatchLog.content_type == content_type,
        TelegramDispatchLog.tier == tier,
        TelegramDispatchLog.status == "sent",
        TelegramDispatchLog.sent_at >= today_start,
        TelegramDispatchLog.sent_at < tomorrow_start,
    ).count()


def signal_quota_remaining(tier: str, daily_limit: int) -> int:
    """
    Calcule combien de signaux il reste à envoyer aujourd’hui
    pour un tier (Basic/Premium/VIP)
    """
    if daily_limit >= 999999:
        return 999999  # VIP illimité

    already_sent = count_sent_today("signal_open", tier)
    remaining = daily_limit - already_sent

    return max(0, remaining)