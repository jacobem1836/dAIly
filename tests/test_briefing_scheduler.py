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
