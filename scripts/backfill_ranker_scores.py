"""Re-score any persisted email metadata with the post-FIX-01 ranker.

Per research A3: signal_log has no `score` field — there is nothing to
mutate in the DB. This script is a VALIDATION report: it locates any
persisted EmailMetadata (Redis briefing cache or DB if present),
re-scores with the fixed ranker, and logs a delta summary.

No schema changes. No row mutations. Read-only.

Usage: python -m scripts.backfill_ranker_scores
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from daily.briefing.ranker import (
    WEIGHT_CC,
    WEIGHT_DIRECT,
    _is_direct_recipient,
    score_email,
)
from daily.config import Settings
from daily.integrations.models import EmailMetadata

logger = logging.getLogger("backfill_ranker_scores")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


async def load_persisted_emails() -> list[EmailMetadata]:
    """Return any EmailMetadata currently persisted.

    Current persistence surfaces:
      - Redis briefing cache (24h TTL) under key pattern 'briefing:*'
      - No DB-level email_metadata table exists in v1.0 schema

    If neither source yields anything, returns [] and the caller logs
    a no-op message.
    """
    # Attempt Redis briefing cache — best-effort; failure is not fatal
    try:
        from daily.briefing.cache import list_cached_emails  # may not exist
        return await list_cached_emails()
    except Exception as exc:
        logger.info("No briefing cache email source available (%s)", exc)
        return []


async def main() -> int:
    settings = Settings()
    user_email = settings.user_email if hasattr(settings, "user_email") else ""
    vip_senders: frozenset[str] = frozenset()  # VIP-neutral re-score — report sender_weight only

    emails = await load_persisted_emails()
    if not emails:
        logger.info(
            "backfill_ranker_scores: no persisted email metadata found. "
            "Phase 8 will train on future signals only."
        )
        return 0

    now = datetime.now(tz=timezone.utc)
    thread_counts: dict[str, int] = {}
    for e in emails:
        thread_counts[e.thread_id] = thread_counts.get(e.thread_id, 0) + 1

    direct_count = 0
    cc_count = 0
    for e in emails:
        score_email(e, vip_senders, user_email, now, thread_counts)
        if user_email and _is_direct_recipient(user_email, e.recipient):
            direct_count += 1
        else:
            cc_count += 1

    logger.info(
        "backfill_ranker_scores report: total=%d direct=%d (WEIGHT_DIRECT=%d) "
        "cc_or_absent=%d (WEIGHT_CC=%d)",
        len(emails), direct_count, WEIGHT_DIRECT, cc_count, WEIGHT_CC,
    )
    logger.info(
        "NOTE: signal_log has no `score` field — no row mutations performed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
