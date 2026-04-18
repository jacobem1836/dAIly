"""Tests for GET /health endpoint — OBS-03.

Covers healthy (200 ok) and degraded (503) paths for DB, Redis, and scheduler probes.
All external dependencies are mocked — no real connections required.

The TestClient triggers the FastAPI lifespan, so we must also mock the lifespan
dependencies (scheduler, async_session for config load, configure_logging).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _make_async_session_ctx(session: AsyncMock) -> MagicMock:
    """Build a mock async context manager for async_session()."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _make_lifespan_session_ctx() -> MagicMock:
    """Build a mock async context manager for the lifespan's BriefingConfig DB query."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # no DB config — use env default
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    return _make_async_session_ctx(mock_session)


def test_health_all_ok():
    """GET /health returns 200 with status ok when DB, Redis, and scheduler all healthy."""
    from daily.main import app

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock())
    session_ctx = _make_async_session_ctx(mock_session)

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.aclose = AsyncMock()

    mock_scheduler = MagicMock()
    mock_scheduler.get_jobs.return_value = [MagicMock()]  # one job = running

    with (
        patch("daily.main.async_session", return_value=session_ctx),
        patch("daily.main.AsyncRedis.from_url", return_value=mock_redis),
        patch("daily.main.scheduler", mock_scheduler),
        patch("daily.main.setup_scheduler"),
        patch("daily.main.configure_logging"),
        patch("daily.main.Settings") as mock_settings_cls,
    ):
        mock_settings_cls.return_value.briefing_schedule_time = "05:00"
        mock_settings_cls.return_value.redis_url = "redis://localhost:6379/0"
        mock_settings_cls.return_value.log_level = "INFO"

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["redis"] == "ok"
    assert body["scheduler"] == "running"


def test_health_db_down():
    """GET /health returns 503 with degraded status when DB probe fails."""
    from daily.main import app

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=Exception("connection refused"))
    session_ctx = _make_async_session_ctx(mock_session)

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.aclose = AsyncMock()

    mock_scheduler = MagicMock()
    mock_scheduler.get_jobs.return_value = [MagicMock()]

    with (
        patch("daily.main.async_session", return_value=session_ctx),
        patch("daily.main.AsyncRedis.from_url", return_value=mock_redis),
        patch("daily.main.scheduler", mock_scheduler),
        patch("daily.main.setup_scheduler"),
        patch("daily.main.configure_logging"),
        patch("daily.main.Settings") as mock_settings_cls,
    ):
        mock_settings_cls.return_value.briefing_schedule_time = "05:00"
        mock_settings_cls.return_value.redis_url = "redis://localhost:6379/0"
        mock_settings_cls.return_value.log_level = "INFO"

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["db"].startswith("error:")


def test_health_redis_down():
    """GET /health returns 503 with degraded status when Redis probe fails."""
    from daily.main import app

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock())
    session_ctx = _make_async_session_ctx(mock_session)

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(side_effect=Exception("redis connection error"))
    mock_redis.aclose = AsyncMock()

    mock_scheduler = MagicMock()
    mock_scheduler.get_jobs.return_value = [MagicMock()]

    with (
        patch("daily.main.async_session", return_value=session_ctx),
        patch("daily.main.AsyncRedis.from_url", return_value=mock_redis),
        patch("daily.main.scheduler", mock_scheduler),
        patch("daily.main.setup_scheduler"),
        patch("daily.main.configure_logging"),
        patch("daily.main.Settings") as mock_settings_cls,
    ):
        mock_settings_cls.return_value.briefing_schedule_time = "05:00"
        mock_settings_cls.return_value.redis_url = "redis://localhost:6379/0"
        mock_settings_cls.return_value.log_level = "INFO"

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["redis"].startswith("error:")


def test_health_no_scheduler_jobs():
    """GET /health returns 503 with scheduler no_jobs when scheduler has no active jobs."""
    from daily.main import app

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock())
    session_ctx = _make_async_session_ctx(mock_session)

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.aclose = AsyncMock()

    mock_scheduler = MagicMock()
    mock_scheduler.get_jobs.return_value = []  # no jobs = degraded

    with (
        patch("daily.main.async_session", return_value=session_ctx),
        patch("daily.main.AsyncRedis.from_url", return_value=mock_redis),
        patch("daily.main.scheduler", mock_scheduler),
        patch("daily.main.setup_scheduler"),
        patch("daily.main.configure_logging"),
        patch("daily.main.Settings") as mock_settings_cls,
    ):
        mock_settings_cls.return_value.briefing_schedule_time = "05:00"
        mock_settings_cls.return_value.redis_url = "redis://localhost:6379/0"
        mock_settings_cls.return_value.log_level = "INFO"

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["scheduler"] == "no_jobs"
    assert body["status"] == "degraded"
