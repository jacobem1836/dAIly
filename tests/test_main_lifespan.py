"""Tests for main.py lifespan: DB config override, env fallback, and DB error fallback."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_lifespan_uses_db_schedule():
    """Lifespan uses schedule_hour/schedule_minute from BriefingConfig when row exists."""
    mock_config = MagicMock()
    mock_config.schedule_hour = 7
    mock_config.schedule_minute = 30

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_config

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
        patch("daily.main.setup_scheduler") as mock_setup,
        patch("daily.main.scheduler", mock_scheduler),
        patch("daily.main.configure_logging"),
        patch("daily.main.Settings") as mock_settings_cls,
    ):
        mock_settings_cls.return_value.briefing_schedule_time = "05:00"
        mock_settings_cls.return_value.log_level = "INFO"
        from fastapi import FastAPI
        from daily.main import lifespan

        app = FastAPI()
        async with lifespan(app):
            pass

    mock_setup.assert_called_once_with(hour=7, minute=30, user_id=1)


@pytest.mark.asyncio
async def test_lifespan_falls_back_to_env_when_no_db_row():
    """Lifespan uses env default when BriefingConfig row is absent (returns None)."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

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
        patch("daily.main.setup_scheduler") as mock_setup,
        patch("daily.main.scheduler", mock_scheduler),
        patch("daily.main.configure_logging"),
        patch("daily.main.Settings") as mock_settings_cls,
    ):
        mock_settings_cls.return_value.briefing_schedule_time = "06:15"
        mock_settings_cls.return_value.log_level = "INFO"
        from fastapi import FastAPI
        from daily.main import lifespan

        app = FastAPI()
        async with lifespan(app):
            pass

    mock_setup.assert_called_once_with(hour=6, minute=15, user_id=1)


@pytest.mark.asyncio
async def test_lifespan_falls_back_to_env_on_db_error():
    """Lifespan uses env default and still starts when DB raises an exception."""
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(side_effect=Exception("DB unavailable"))
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_scheduler = MagicMock()
    mock_scheduler.start = MagicMock()
    mock_scheduler.shutdown = MagicMock()

    with (
        patch("daily.main.async_session", return_value=mock_ctx),
        patch("daily.main.setup_scheduler") as mock_setup,
        patch("daily.main.scheduler", mock_scheduler),
        patch("daily.main.configure_logging"),
        patch("daily.main.Settings") as mock_settings_cls,
    ):
        mock_settings_cls.return_value.briefing_schedule_time = "05:00"
        mock_settings_cls.return_value.log_level = "INFO"
        from fastapi import FastAPI
        from daily.main import lifespan

        app = FastAPI()
        async with lifespan(app):
            pass

    mock_setup.assert_called_once_with(hour=5, minute=0, user_id=1)
