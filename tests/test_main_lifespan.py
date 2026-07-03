"""Tests for main.py lifespan: multi-user cron registration and DB error fallback."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_lifespan_registers_one_job_per_briefing_config_row():
    """Lifespan calls setup_scheduler_for_user once per BriefingConfig row,
    passing each row's timezone through (audit M1 DST fix)."""
    row1 = MagicMock()
    row1.user_id = 1
    row1.schedule_hour = 5
    row1.schedule_minute = 0
    row1.timezone = "UTC"

    row2 = MagicMock()
    row2.user_id = 2
    row2.schedule_hour = 14
    row2.schedule_minute = 30
    row2.timezone = "Australia/Brisbane"

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [row1, row2]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_scheduler = MagicMock()
    mock_scheduler.start = MagicMock()
    mock_scheduler.shutdown = MagicMock()

    with (
        patch("daily.main.async_session", return_value=mock_ctx),
        patch("daily.main.setup_scheduler_for_user") as mock_setup,
        patch("daily.main.setup_token_refresh_job") as mock_setup_refresh,
        patch("daily.main.scheduler", mock_scheduler),
    ):
        from fastapi import FastAPI
        from daily.main import lifespan

        app = FastAPI()
        async with lifespan(app):
            pass

    assert mock_setup.call_count == 2
    calls = {call.kwargs["user_id"]: call.kwargs for call in mock_setup.call_args_list}
    assert calls[1]["hour"] == 5 and calls[1]["minute"] == 0
    assert calls[1]["timezone"] == "UTC"
    assert calls[2]["hour"] == 14 and calls[2]["minute"] == 30
    assert calls[2]["timezone"] == "Australia/Brisbane"
    mock_scheduler.start.assert_called_once()
    mock_scheduler.shutdown.assert_called_once_with(wait=False)
    # Audit C2: periodic token-refresh job is registered on every startup.
    mock_setup_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_lifespan_zero_jobs_when_no_config_rows():
    """Lifespan starts scheduler with zero jobs when BriefingConfig table is empty."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_scheduler = MagicMock()
    mock_scheduler.start = MagicMock()
    mock_scheduler.shutdown = MagicMock()

    with (
        patch("daily.main.async_session", return_value=mock_ctx),
        patch("daily.main.setup_scheduler_for_user") as mock_setup,
        patch("daily.main.setup_token_refresh_job") as mock_setup_refresh,
        patch("daily.main.scheduler", mock_scheduler),
    ):
        from fastapi import FastAPI
        from daily.main import lifespan

        app = FastAPI()
        async with lifespan(app):
            pass

    mock_setup.assert_not_called()
    mock_scheduler.start.assert_called_once()
    mock_setup_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_lifespan_starts_with_no_jobs_on_db_error():
    """Lifespan does not crash when DB raises; scheduler still starts (T-21-05-02)."""
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(side_effect=Exception("DB unavailable"))
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_scheduler = MagicMock()
    mock_scheduler.start = MagicMock()
    mock_scheduler.shutdown = MagicMock()

    with (
        patch("daily.main.async_session", return_value=mock_ctx),
        patch("daily.main.setup_scheduler_for_user") as mock_setup,
        patch("daily.main.setup_token_refresh_job") as mock_setup_refresh,
        patch("daily.main.scheduler", mock_scheduler),
    ):
        from fastapi import FastAPI
        from daily.main import lifespan

        app = FastAPI()
        async with lifespan(app):
            pass

    mock_setup.assert_not_called()
    mock_scheduler.start.assert_called_once()
    mock_setup_refresh.assert_called_once()
