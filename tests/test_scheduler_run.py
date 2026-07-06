"""Unit tests for briefing/scheduler.py _scheduled_pipeline_run and helpers.

Covers:
- _scheduled_pipeline_run: success path calls run_briefing_pipeline
- _scheduled_pipeline_run: exception from _build_pipeline_kwargs is caught, logged, no crash
- _scheduled_pipeline_run: exception from run_briefing_pipeline is caught, logged, no crash
- _scheduled_pipeline_run: redis.aclose() called in finally block
- _try_acquire_run_lock / distributed run-lock (audit M2)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# _scheduled_pipeline_run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scheduled_pipeline_run_calls_run_briefing_pipeline():
    """Success path: _scheduled_pipeline_run calls run_briefing_pipeline with kwargs."""
    from daily.briefing.scheduler import _scheduled_pipeline_run

    fake_redis = AsyncMock()
    fake_redis.aclose = AsyncMock()
    fake_kwargs = {"redis": fake_redis, "email_adapters": []}

    with (
        patch(
            "daily.briefing.scheduler._build_pipeline_kwargs",
            new=AsyncMock(return_value=fake_kwargs),
        ),
        patch(
            "daily.briefing.scheduler.run_briefing_pipeline",
            new=AsyncMock(),
        ) as mock_run,
    ):
        await _scheduled_pipeline_run(user_id=1)

    mock_run.assert_awaited_once_with(user_id=1, **fake_kwargs)


@pytest.mark.asyncio
async def test_scheduled_pipeline_run_closes_redis_on_success():
    """redis.aclose() is called even on successful completion."""
    from daily.briefing.scheduler import _scheduled_pipeline_run

    fake_redis = AsyncMock()
    fake_redis.aclose = AsyncMock()
    fake_kwargs = {"redis": fake_redis}

    with (
        patch(
            "daily.briefing.scheduler._build_pipeline_kwargs",
            new=AsyncMock(return_value=fake_kwargs),
        ),
        patch(
            "daily.briefing.scheduler.run_briefing_pipeline",
            new=AsyncMock(),
        ),
    ):
        await _scheduled_pipeline_run(user_id=1)

    fake_redis.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_scheduled_pipeline_run_handles_build_kwargs_exception():
    """Exception from _build_pipeline_kwargs is caught — function does not raise."""
    from daily.briefing.scheduler import _scheduled_pipeline_run

    with (
        patch(
            "daily.briefing.scheduler._build_pipeline_kwargs",
            new=AsyncMock(side_effect=RuntimeError("DB unavailable")),
        ),
        patch(
            "daily.briefing.scheduler.run_briefing_pipeline",
            new=AsyncMock(),
        ) as mock_run,
    ):
        # Must not raise
        await _scheduled_pipeline_run(user_id=99)

    # Pipeline should not have been called
    mock_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_scheduled_pipeline_run_handles_pipeline_exception():
    """Exception from run_briefing_pipeline is caught — function does not raise."""
    from daily.briefing.scheduler import _scheduled_pipeline_run

    fake_redis = AsyncMock()
    fake_redis.aclose = AsyncMock()
    fake_kwargs = {"redis": fake_redis}

    with (
        patch(
            "daily.briefing.scheduler._build_pipeline_kwargs",
            new=AsyncMock(return_value=fake_kwargs),
        ),
        patch(
            "daily.briefing.scheduler.run_briefing_pipeline",
            new=AsyncMock(side_effect=RuntimeError("pipeline failed")),
        ),
    ):
        # Must not raise
        await _scheduled_pipeline_run(user_id=7)

    # Redis should still be cleaned up
    fake_redis.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_scheduled_pipeline_run_no_redis_in_kwargs():
    """When _build_pipeline_kwargs raises before redis is created, no aclose crash."""
    from daily.briefing.scheduler import _scheduled_pipeline_run

    with (
        patch(
            "daily.briefing.scheduler._build_pipeline_kwargs",
            new=AsyncMock(side_effect=ConnectionError("cannot connect")),
        ),
        patch(
            "daily.briefing.scheduler.run_briefing_pipeline",
            new=AsyncMock(),
        ),
    ):
        # Must not raise even with no redis in kwargs
        await _scheduled_pipeline_run(user_id=5)


# ---------------------------------------------------------------------------
# Distributed run-lock (audit M2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_try_acquire_run_lock_succeeds_when_unheld():
    """_try_acquire_run_lock returns True and sets the key when nobody holds it."""
    import fakeredis.aioredis as fake_aioredis

    from daily.briefing.scheduler import _try_acquire_run_lock
    from daily.config import Settings

    fake_client = fake_aioredis.FakeRedis()
    settings = Settings(redis_url="redis://localhost:6379/0")

    with patch("daily.briefing.scheduler.Redis.from_url", return_value=fake_client):
        acquired = await _try_acquire_run_lock("lock:test:1", 60, settings)

    assert acquired is True
    assert await fake_client.get("lock:test:1") is not None
    await fake_client.aclose()


@pytest.mark.asyncio
async def test_try_acquire_run_lock_fails_when_already_held():
    """_try_acquire_run_lock returns False when the key is already set (SET NX semantics)."""
    import fakeredis.aioredis as fake_aioredis

    from daily.briefing.scheduler import _try_acquire_run_lock
    from daily.config import Settings

    fake_client = fake_aioredis.FakeRedis()
    await fake_client.set("lock:test:2", "someone-else", nx=True, ex=60)
    settings = Settings(redis_url="redis://localhost:6379/0")

    with patch("daily.briefing.scheduler.Redis.from_url", return_value=fake_client):
        acquired = await _try_acquire_run_lock("lock:test:2", 60, settings)

    assert acquired is False
    await fake_client.aclose()


@pytest.mark.asyncio
async def test_try_acquire_run_lock_fails_open_when_redis_unavailable():
    """_try_acquire_run_lock returns True (fail open) if Redis is unreachable.

    A distributed lock is a multi-replica optimization, not a correctness
    requirement — a single-replica deployment (or a transient Redis outage)
    must never silently skip a scheduled briefing.
    """
    from daily.briefing.scheduler import _try_acquire_run_lock
    from daily.config import Settings

    broken_client = AsyncMock()
    broken_client.set = AsyncMock(side_effect=ConnectionError("redis down"))
    broken_client.aclose = AsyncMock()
    settings = Settings(redis_url="redis://localhost:6379/0")

    with patch("daily.briefing.scheduler.Redis.from_url", return_value=broken_client):
        acquired = await _try_acquire_run_lock("lock:test:3", 60, settings)

    assert acquired is True
    broken_client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_scheduled_pipeline_run_skips_when_lock_not_acquired():
    """_scheduled_pipeline_run does not call run_briefing_pipeline when the lock is held elsewhere."""
    from daily.briefing.scheduler import _scheduled_pipeline_run

    with (
        patch(
            "daily.briefing.scheduler._try_acquire_run_lock",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "daily.briefing.scheduler._build_pipeline_kwargs",
            new=AsyncMock(),
        ) as mock_build_kwargs,
        patch(
            "daily.briefing.scheduler.run_briefing_pipeline",
            new=AsyncMock(),
        ) as mock_run,
    ):
        await _scheduled_pipeline_run(user_id=42)

    mock_build_kwargs.assert_not_awaited()
    mock_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_scheduled_pipeline_run_proceeds_when_lock_acquired():
    """_scheduled_pipeline_run calls run_briefing_pipeline when the lock is acquired."""
    from daily.briefing.scheduler import _scheduled_pipeline_run

    fake_redis = AsyncMock()
    fake_redis.aclose = AsyncMock()
    fake_kwargs = {"redis": fake_redis}

    with (
        patch(
            "daily.briefing.scheduler._try_acquire_run_lock",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "daily.briefing.scheduler._build_pipeline_kwargs",
            new=AsyncMock(return_value=fake_kwargs),
        ),
        patch(
            "daily.briefing.scheduler.run_briefing_pipeline",
            new=AsyncMock(),
        ) as mock_run,
    ):
        await _scheduled_pipeline_run(user_id=43)

    mock_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_token_refresh_job_skips_when_lock_not_acquired():
    """_run_token_refresh_job does not call refresh_expiring_tokens when the lock is held elsewhere."""
    from daily.briefing.scheduler import _run_token_refresh_job

    with (
        patch(
            "daily.briefing.scheduler._try_acquire_run_lock",
            new=AsyncMock(return_value=False),
        ),
        patch("daily.vault.crypto.load_vault_key", return_value=b"k" * 32),
        patch(
            "daily.vault.refresh.refresh_expiring_tokens", new=AsyncMock()
        ) as mock_refresh,
    ):
        await _run_token_refresh_job()

    mock_refresh.assert_not_awaited()
