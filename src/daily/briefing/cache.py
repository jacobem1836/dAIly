"""
Briefing Redis cache: read/write with 24h TTL (D-14).

Cache key convention: briefing:{user_id}:{date} where date is always UTC.
UTC date ensures consistent keys regardless of server timezone — avoids
off-by-one errors at midnight in non-UTC timezones.

Only the BriefingOutput (redacted narrative + metadata) is stored in Redis.
Raw bodies and context are never written to cache (SEC-02/T-02-11).
"""

import json
from datetime import date, datetime

from redis.asyncio import Redis

from daily.briefing.models import BriefingOutput

CACHE_TTL = 86400  # 24 hours per D-14


def _cache_key(user_id: int, briefing_date: date) -> str:
    """Cache key using UTC date. Convention: all dates in cache keys are UTC.

    Format: briefing:{user_id}:{YYYY-MM-DD}
    Example: briefing:1:2026-04-05
    """
    return f"briefing:{user_id}:{briefing_date.isoformat()}"


async def cache_briefing(redis: Redis, user_id: int, output: BriefingOutput) -> None:
    """Write a BriefingOutput to Redis with TTL=86400 (24h).

    Uses UTC date from output.generated_at for the cache key.
    Only stores the narrative, generated_at, and version — never raw bodies
    (SEC-02/T-02-11: raw content is in-memory only during pipeline execution).

    Args:
        redis: Async Redis connection.
        user_id: User ID for the cache key namespace.
        output: BriefingOutput to cache.
    """
    key = _cache_key(user_id, output.generated_at.date())
    payload = {
        "narrative": output.narrative,
        "generated_at": output.generated_at.isoformat(),
        "version": output.version,
    }
    await redis.set(key, json.dumps(payload), ex=CACHE_TTL)


async def get_briefing(
    redis: Redis, user_id: int, briefing_date: date
) -> BriefingOutput | None:
    """Retrieve a cached BriefingOutput from Redis.

    Args:
        redis: Async Redis connection.
        user_id: User ID for the cache key namespace.
        briefing_date: UTC date of the briefing to retrieve.

    Returns:
        BriefingOutput if found in cache, None on cache miss.
    """
    key = _cache_key(user_id, briefing_date)
    raw = await redis.get(key)
    if raw is None:
        return None
    data = json.loads(raw)
    return BriefingOutput(
        narrative=data["narrative"],
        generated_at=datetime.fromisoformat(data["generated_at"]),
        version=data["version"],
    )
