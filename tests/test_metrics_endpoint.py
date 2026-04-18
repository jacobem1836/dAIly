"""Tests for GET /metrics endpoint — OBS-04.

Covers response shape, signal count aggregation, memory entry count, and
latency average from Redis. All external dependencies are mocked.

The TestClient triggers the FastAPI lifespan, so we mock the lifespan's
dependencies (scheduler, configure_logging) alongside the endpoint dependencies.

NOTE: The lifespan calls async_session() once (to read BriefingConfig).
The /metrics endpoint calls async_session() once for DB queries.
We use a side_effect list on async_session (the callable) so each call
returns a fresh context manager — preventing StopIteration errors.
"""

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from fastapi.testclient import TestClient


def _make_session_ctx_from_results(results: list) -> MagicMock:
    """Build an async context manager whose session.execute() yields from results."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=results)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _make_lifespan_session_ctx() -> MagicMock:
    """Lifespan queries BriefingConfig — returns None (use env default)."""
    lifespan_result = MagicMock()
    lifespan_result.scalar_one_or_none.return_value = None
    return _make_session_ctx_from_results([lifespan_result])


def _make_redis_with_keys(key_value_pairs: list[tuple[bytes, bytes]]) -> AsyncMock:
    """Build a mock AsyncRedis that yields the given (key, value) pairs from scan_iter.

    scan_iter is an async generator, so we use an async generator function.
    """
    keys = [kv[0] for kv in key_value_pairs]
    values = {kv[0]: kv[1] for kv in key_value_pairs}

    async def _scan_iter(pattern: str):
        for key in keys:
            yield key

    mock_redis = AsyncMock()
    mock_redis.scan_iter = _scan_iter
    mock_redis.get = AsyncMock(side_effect=lambda k: values.get(k))
    mock_redis.aclose = AsyncMock()
    return mock_redis


def test_metrics_returns_all_fields():
    """GET /metrics returns briefing_latency_avg_s, signals_7d, and memory_entries."""
    from daily.main import app

    # Lifespan session ctx (BriefingConfig query)
    lifespan_ctx = _make_lifespan_session_ctx()

    # Endpoint session ctx (signal counts + memory count in one session)
    signal_result = MagicMock()
    signal_result.all.return_value = [("skip", 3), ("expand", 10)]
    memory_result = MagicMock()
    memory_result.scalar_one.return_value = 42
    endpoint_ctx = _make_session_ctx_from_results([signal_result, memory_result])

    # async_session is called once by lifespan and once by the endpoint
    mock_async_session = MagicMock(side_effect=[lifespan_ctx, endpoint_ctx])

    # Redis: one latency key
    mock_redis = _make_redis_with_keys([(b"briefing:1:latency_s", b"4.5")])

    mock_scheduler = MagicMock()
    mock_scheduler.start = MagicMock()
    mock_scheduler.shutdown = MagicMock()

    with (
        patch("daily.main.async_session", mock_async_session),
        patch("daily.main.AsyncRedis.from_url", return_value=mock_redis),
        patch("daily.main.scheduler", mock_scheduler),
        patch("daily.main.setup_scheduler"),
        patch("daily.main.configure_logging"),
        patch("daily.main.Settings") as mock_settings_cls,
    ):
        mock_settings_cls.return_value.briefing_schedule_time = "05:00"
        mock_settings_cls.return_value.redis_url = "redis://localhost:6379/0"
        mock_settings_cls.return_value.log_level = "INFO"

        with TestClient(app, raise_server_exceptions=True) as client:
            response = client.get("/metrics")

    assert response.status_code == 200
    body = response.json()
    assert "briefing_latency_avg_s" in body
    assert "signals_7d" in body
    assert "memory_entries" in body
    assert body["memory_entries"] == 42
    assert body["signals_7d"] == {"skip": 3, "expand": 10}
    assert body["briefing_latency_avg_s"] == pytest.approx(4.5)


def test_metrics_empty_data():
    """GET /metrics returns zeros and empty dicts when no data exists."""
    from daily.main import app

    lifespan_ctx = _make_lifespan_session_ctx()

    signal_result = MagicMock()
    signal_result.all.return_value = []
    memory_result = MagicMock()
    memory_result.scalar_one.return_value = 0
    endpoint_ctx = _make_session_ctx_from_results([signal_result, memory_result])

    mock_async_session = MagicMock(side_effect=[lifespan_ctx, endpoint_ctx])

    # Redis: no latency keys
    mock_redis = _make_redis_with_keys([])

    mock_scheduler = MagicMock()
    mock_scheduler.start = MagicMock()
    mock_scheduler.shutdown = MagicMock()

    with (
        patch("daily.main.async_session", mock_async_session),
        patch("daily.main.AsyncRedis.from_url", return_value=mock_redis),
        patch("daily.main.scheduler", mock_scheduler),
        patch("daily.main.setup_scheduler"),
        patch("daily.main.configure_logging"),
        patch("daily.main.Settings") as mock_settings_cls,
    ):
        mock_settings_cls.return_value.briefing_schedule_time = "05:00"
        mock_settings_cls.return_value.redis_url = "redis://localhost:6379/0"
        mock_settings_cls.return_value.log_level = "INFO"

        with TestClient(app, raise_server_exceptions=True) as client:
            response = client.get("/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["briefing_latency_avg_s"] == 0.0
    assert body["signals_7d"] == {}
    assert body["memory_entries"] == 0


def test_metrics_latency_averages_multiple():
    """GET /metrics computes average when multiple latency keys exist."""
    from daily.main import app

    lifespan_ctx = _make_lifespan_session_ctx()

    signal_result = MagicMock()
    signal_result.all.return_value = []
    memory_result = MagicMock()
    memory_result.scalar_one.return_value = 0
    endpoint_ctx = _make_session_ctx_from_results([signal_result, memory_result])

    mock_async_session = MagicMock(side_effect=[lifespan_ctx, endpoint_ctx])

    # Redis: three latency keys — 2.0, 4.0, 6.0 → average should be 4.0
    mock_redis = _make_redis_with_keys([
        (b"briefing:1:latency_s", b"2.0"),
        (b"briefing:2:latency_s", b"4.0"),
        (b"briefing:3:latency_s", b"6.0"),
    ])

    mock_scheduler = MagicMock()
    mock_scheduler.start = MagicMock()
    mock_scheduler.shutdown = MagicMock()

    with (
        patch("daily.main.async_session", mock_async_session),
        patch("daily.main.AsyncRedis.from_url", return_value=mock_redis),
        patch("daily.main.scheduler", mock_scheduler),
        patch("daily.main.setup_scheduler"),
        patch("daily.main.configure_logging"),
        patch("daily.main.Settings") as mock_settings_cls,
    ):
        mock_settings_cls.return_value.briefing_schedule_time = "05:00"
        mock_settings_cls.return_value.redis_url = "redis://localhost:6379/0"
        mock_settings_cls.return_value.log_level = "INFO"

        with TestClient(app, raise_server_exceptions=True) as client:
            response = client.get("/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["briefing_latency_avg_s"] == pytest.approx(4.0)
