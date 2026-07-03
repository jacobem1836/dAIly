"""Tests for daily.auth.ratelimit (security fix, wave 1 audit remediation).

Covers the fixed-window RateLimiter dependency in isolation, backed by
fakeredis — no live Redis needed. Endpoint-level rate-limit behavior (429 on
breach for the real auth routes) is covered in test_auth_pairing.py.
"""
from unittest.mock import MagicMock

import pytest

from daily.auth.ratelimit import RateLimiter, client_ip


@pytest.fixture
async def fake_redis():
    import fakeredis.aioredis as fake_aioredis

    client = fake_aioredis.FakeRedis()
    yield client
    await client.aclose()


def _fake_request(ip: str = "127.0.0.1"):
    request = MagicMock()
    request.client.host = ip
    return request


def test_client_ip_returns_host():
    assert client_ip(_fake_request("10.0.0.5")) == "10.0.0.5"


def test_client_ip_falls_back_when_no_client():
    request = MagicMock()
    request.client = None
    assert client_ip(request) == "unknown"


@pytest.mark.asyncio
async def test_requests_under_limit_pass(fake_redis):
    limiter = RateLimiter("test_bucket", limit=3, window_seconds=60)
    request = _fake_request()
    for _ in range(3):
        await limiter(request, redis=fake_redis)  # must not raise


@pytest.mark.asyncio
async def test_request_over_limit_raises_429(fake_redis):
    from fastapi import HTTPException

    limiter = RateLimiter("test_bucket_2", limit=2, window_seconds=60)
    request = _fake_request()
    await limiter(request, redis=fake_redis)
    await limiter(request, redis=fake_redis)
    with pytest.raises(HTTPException) as exc:
        await limiter(request, redis=fake_redis)
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_different_ips_have_independent_counters(fake_redis):
    limiter = RateLimiter("test_bucket_3", limit=1, window_seconds=60)
    await limiter(_fake_request("1.1.1.1"), redis=fake_redis)  # uses up ip A's budget
    await limiter(_fake_request("2.2.2.2"), redis=fake_redis)  # ip B still has budget


@pytest.mark.asyncio
async def test_different_buckets_have_independent_counters(fake_redis):
    request = _fake_request()
    limiter_a = RateLimiter("bucket_a", limit=1, window_seconds=60)
    limiter_b = RateLimiter("bucket_b", limit=1, window_seconds=60)
    await limiter_a(request, redis=fake_redis)
    await limiter_b(request, redis=fake_redis)  # separate bucket, must not raise
