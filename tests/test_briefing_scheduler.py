"""Tests for APScheduler briefing scheduler (scheduler.py)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_scheduler_reschedule():
    """update_schedule calls scheduler.reschedule_job with CronTrigger params."""
    from apscheduler.triggers.cron import CronTrigger

    from daily.briefing.scheduler import scheduler, update_schedule

    with patch.object(scheduler, "reschedule_job") as mock_reschedule:
        update_schedule(10, 30)
        mock_reschedule.assert_called_once()
        call_kwargs = mock_reschedule.call_args
        assert call_kwargs[0][0] == "briefing_precompute"
        trigger = call_kwargs[1]["trigger"]
        assert isinstance(trigger, CronTrigger)


@pytest.mark.asyncio
async def test_setup_scheduler_adds_job():
    """setup_scheduler adds a job with _scheduled_pipeline_run as the callable."""
    from daily.briefing.scheduler import scheduler, setup_scheduler, _scheduled_pipeline_run

    with patch.object(scheduler, "add_job") as mock_add_job:
        setup_scheduler(hour=5, minute=30, user_id=1)
        mock_add_job.assert_called_once()
        call_args = mock_add_job.call_args
        # First positional arg should be _scheduled_pipeline_run
        assert call_args[0][0] is _scheduled_pipeline_run
        # Should have replace_existing=True
        assert call_args[1].get("replace_existing") is True


# ---------------------------------------------------------------------------
# 08-04: db_session session lifecycle tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scheduled_pipeline_run_opens_session():
    """_scheduled_pipeline_run opens a session and passes it as db_session to run_briefing_pipeline."""
    from daily.briefing.scheduler import _scheduled_pipeline_run

    mock_session = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_async_session = MagicMock(return_value=mock_cm)

    mock_redis = AsyncMock()
    mock_pipeline_kwargs = {
        "email_adapters": [],
        "calendar_adapters": [],
        "message_adapters": [],
        "vip_senders": frozenset(),
        "user_email": "me@example.com",
        "top_n": 5,
        "redis": mock_redis,
        "openai_client": AsyncMock(),
        "preferences": None,
    }

    mock_run_pipeline = AsyncMock()

    with patch("daily.briefing.scheduler._build_pipeline_kwargs", AsyncMock(return_value=mock_pipeline_kwargs)), \
         patch("daily.briefing.scheduler.async_session", mock_async_session), \
         patch("daily.briefing.scheduler.run_briefing_pipeline", mock_run_pipeline):
        await _scheduled_pipeline_run(user_id=1)

    mock_run_pipeline.assert_called_once()
    call_kwargs = mock_run_pipeline.call_args[1]
    assert call_kwargs.get("db_session") is not None, (
        "run_briefing_pipeline was called without db_session — session not opened"
    )
    assert call_kwargs["db_session"] is mock_session


@pytest.mark.asyncio
async def test_scheduled_pipeline_run_closes_session_on_error():
    """Session __aexit__ is called even when run_briefing_pipeline raises, and redis is closed."""
    from daily.briefing.scheduler import _scheduled_pipeline_run

    mock_session = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_async_session = MagicMock(return_value=mock_cm)

    mock_redis = AsyncMock()
    mock_pipeline_kwargs = {
        "email_adapters": [],
        "calendar_adapters": [],
        "message_adapters": [],
        "vip_senders": frozenset(),
        "user_email": "me@example.com",
        "top_n": 5,
        "redis": mock_redis,
        "openai_client": AsyncMock(),
        "preferences": None,
    }

    failing_pipeline = AsyncMock(side_effect=RuntimeError("pipeline exploded"))

    with patch("daily.briefing.scheduler._build_pipeline_kwargs", AsyncMock(return_value=mock_pipeline_kwargs)), \
         patch("daily.briefing.scheduler.async_session", mock_async_session), \
         patch("daily.briefing.scheduler.run_briefing_pipeline", failing_pipeline):
        # Should not raise — exception is caught by the outer try/except
        await _scheduled_pipeline_run(user_id=1)

    # Session context manager __aexit__ must have been called (cleanup on error)
    mock_cm.__aexit__.assert_called_once()

    # Redis must still be closed in finally block
    mock_redis.aclose.assert_called_once()


@pytest.mark.asyncio
async def test_build_pipeline_kwargs_returns_required_keys():
    """_build_pipeline_kwargs returns dict with all pipeline dependency keys."""
    from daily.briefing.scheduler import _build_pipeline_kwargs
    from daily.config import Settings

    # Mock DB queries
    mock_session = AsyncMock()
    mock_result_vip = MagicMock()
    mock_result_vip.fetchall.return_value = [("vip@example.com",)]
    mock_result_tokens = MagicMock()
    mock_result_tokens.scalars.return_value.all.return_value = []

    mock_session.execute = AsyncMock(
        side_effect=[mock_result_vip, mock_result_tokens]
    )

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("daily.briefing.scheduler.async_session", return_value=mock_ctx):
        settings = Settings(
            redis_url="redis://localhost:6379/0",
            openai_api_key="test-key",
            briefing_email_top_n=5,
        )
        result = await _build_pipeline_kwargs(user_id=1, settings=settings)

    required_keys = {
        "email_adapters",
        "calendar_adapters",
        "message_adapters",
        "vip_senders",
        "user_email",
        "top_n",
        "redis",
        "openai_client",
    }
    assert required_keys == set(result.keys()), (
        f"Missing keys: {required_keys - set(result.keys())}"
    )
    assert "vip@example.com" in result["vip_senders"]
    assert result["top_n"] == 5
