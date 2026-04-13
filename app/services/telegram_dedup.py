import hashlib
from datetime import datetime, timedelta

from app.extensions import db
from app.models.telegram_dispatch_log import TelegramDispatchLog


MAX_KEY_LEN = 255
MAX_REF_LEN = 255


def normalize_text(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def hash_text(text: str) -> str:
    normalized = normalize_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def safe_ref(text: str | None, max_len: int = MAX_REF_LEN) -> str | None:
    if not text:
        return None

    text = str(text).strip()
    if len(text) <= max_len:
        return text

    return text[: max_len - 3] + "..."


def safe_key(prefix: str, raw_value: str | None) -> str:
    raw_value = str(raw_value or "").strip()

    if not raw_value:
        return prefix

    candidate = f"{prefix}:{raw_value}"

    if len(candidate) <= MAX_KEY_LEN:
        return candidate

    return f"{prefix}:sha256:{hash_text(raw_value)}"


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
    safe_dedup = dedup_key
    if len(str(safe_dedup)) > MAX_KEY_LEN:
        safe_dedup = safe_key(f"{content_type}:{tier}", dedup_key)

    log = TelegramDispatchLog(
        content_type=content_type,
        tier=tier,
        dedup_key=safe_dedup,
        content_hash=content_hash or (hash_text(content_text or "") if content_text else None),
        content_ref=safe_ref(content_ref),
        sent_at=datetime.utcnow(),
        status=status,
    )
    db.session.add(log)
    db.session.commit()
    return log


def signal_event_key(event_type: str, tier: str, signal_id: int | None, trade_id: str | None) -> str:
    signal_part = str(signal_id or "none")
    trade_part = str(trade_id or "none")
    return safe_key(event_type, f"{tier}:signal={signal_part}:trade={trade_part}")


def news_digest_key(tier: str, digest_date: str, slot: str, version: str = "v1") -> str:
    return safe_key("daily_news", f"{tier}:{digest_date}:{slot}:{version}")


def briefing_key(briefing_type: str, tier: str, briefing_date: str, slot: str, version: str = "v1") -> str:
    return safe_key(briefing_type, f"{tier}:{briefing_date}:{slot}:{version}")


def breaking_news_key(tier: str, article_id: str | None = None, article_url: str | None = None) -> str:
    ref = article_id or article_url or "unknown"
    return safe_key("breaking_news", f"{tier}:{ref}")


def purge_old_dispatch_logs(days: int = 30) -> int:
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
    if daily_limit >= 999999:
        return 999999

    already_sent = count_sent_today("signal_open", tier)
    remaining = daily_limit - already_sent

    return max(0, remaining)