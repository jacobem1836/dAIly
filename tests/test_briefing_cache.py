"""Tests for briefing Redis cache (cache.py)."""

import json
from datetime import date, datetime, timezone

import pytest

from fakeredis import FakeAsyncRedis

from daily.briefing.models import BriefingOutput


@pytest.fixture
def briefing_output() -> BriefingOutput:
    return BriefingOutput(
        narrative="Good morning. Here is your briefing for today.",
        generated_at=datetime(2026, 4, 5, 5, 0, 0, tzinfo=timezone.utc),
        version=1,
    )


@pytest.fixture
async def redis():
    return FakeAsyncRedis()


@pytest.mark.asyncio
async def test_cache_briefing(briefing_output):
    """cache_briefing stores JSON in Redis with key briefing:{user_id}:{date} and TTL=86400."""
    from daily.briefing.cache import cache_briefing, CACHE_TTL

    redis = FakeAsyncRedis()
    await cache_briefing(redis, user_id=1, output=briefing_output)

    # Verify the key exists and has correct TTL
    key = "briefing:1:2026-04-05"
    raw = await redis.get(key)
    assert raw is not None, "Cache key not found after cache_briefing"

    data = json.loads(raw)
    assert data["narrative"] == briefing_output.narrative
    assert data["version"] == briefing_output.version

    ttl = await redis.ttl(key)
    assert 86300 <= ttl <= CACHE_TTL, f"TTL {ttl} not in expected range"


@pytest.mark.asyncio
async def test_get_briefing_hit(briefing_output):
    """After caching, get_briefing returns the BriefingOutput."""
    from daily.briefing.cache import cache_briefing, get_briefing

    redis = FakeAsyncRedis()
    await cache_briefing(redis, user_id=1, output=briefing_output)

    result = await get_briefing(redis, user_id=1, briefing_date=date(2026, 4, 5))
    assert result is not None
    assert result.narrative == briefing_output.narrative
    assert result.version == briefing_output.version


@pytest.mark.asyncio
async def test_get_briefing_miss():
    """get_briefing returns None when no cached briefing exists."""
    from daily.briefing.cache import get_briefing

    redis = FakeAsyncRedis()
    result = await get_briefing(redis, user_id=1, briefing_date=date(2026, 4, 5))
    assert result is None


@pytest.mark.asyncio
async def test_cache_key_format(briefing_output):
    """Cache key follows pattern briefing:1:2026-04-05 (UTC date)."""
    from daily.briefing.cache import cache_briefing

    redis = FakeAsyncRedis()
    await cache_briefing(redis, user_id=1, output=briefing_output)

    # Verify exact key format
    keys = await redis.keys("briefing:*")
    assert len(keys) == 1
    key = keys[0].decode() if isinstance(keys[0], bytes) else keys[0]
    assert key == "briefing:1:2026-04-05"
