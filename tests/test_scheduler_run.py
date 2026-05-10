"""Unit tests for briefing/scheduler.py _scheduled_pipeline_run and helpers.

Covers:
- _scheduled_pipeline_run: success path calls run_briefing_pipeline
- _scheduled_pipeline_run: exception from _build_pipeline_kwargs is caught, logged, no crash
- _scheduled_pipeline_run: exception from run_briefing_pipeline is caught, logged, no crash
- _scheduled_pipeline_run: redis.aclose() called in finally block
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
