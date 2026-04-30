"""Tests for daily.worker.state — load_user_session_state async context manager.

RED phase: these tests are written before the implementation exists.
All imports from daily.worker.state will fail until the module is created.
"""
import re
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest_plugins = ["pytest_asyncio"]


# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------

def _make_mock_checkpointer():
    """Return an async context manager mock that yields a checkpointer stub."""
    checkpointer = MagicMock()
    checkpointer.setup = AsyncMock()

    @asynccontextmanager
    async def _ctx(*args, **kwargs):
        yield checkpointer

    return _ctx, checkpointer


def _make_mock_redis():
    redis = MagicMock()
    redis.aclose = AsyncMock()
    return redis


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_bundle_populated(monkeypatch):
    """SessionBundle contains graph, config, initial_state, and briefing_narrative."""
    from daily.worker.state import load_user_session_state, SessionBundle

    sentinel_graph = object()
    fake_initial_state = {
        "briefing_narrative": "Good morning. Three things.",
        "active_user_id": 1,
        "preferences": {},
        "email_context": [],
    }

    ctx_factory, _cp = _make_mock_checkpointer()

    with (
        patch("daily.worker.state.AsyncPostgresSaver.from_conn_string", ctx_factory),
        patch("daily.worker.state._resolve_email_adapters", AsyncMock(return_value=[])),
        patch("daily.worker.state.build_graph", return_value=sentinel_graph),
        patch("daily.worker.state.Redis.from_url", return_value=_make_mock_redis()),
        patch("daily.worker.state.initialize_session_state", AsyncMock(return_value=fake_initial_state)),
        patch("daily.worker.state.set_email_adapters"),
    ):
        from daily.config import Settings

        settings = Settings(
            database_url="postgresql+asyncpg://test/test",
            database_url_psycopg="postgresql+psycopg://test/test",
            redis_url="redis://localhost",
            openai_api_key="sk-test",
            vault_key="",
        )

        async with load_user_session_state(user_id=1, settings=settings) as bundle:
            assert isinstance(bundle, SessionBundle)
            assert bundle.graph is sentinel_graph
            assert bundle.initial_state == fake_initial_state
            assert bundle.briefing_narrative == "Good morning. Three things."
            assert bundle.config is not None


@pytest.mark.asyncio
async def test_thread_id_format(monkeypatch):
    """bundle.config['configurable']['thread_id'] matches user-1-YYYY-MM-DD."""
    from daily.worker.state import load_user_session_state

    fake_initial_state = {
        "briefing_narrative": "Morning brief.",
        "active_user_id": 1,
        "preferences": {},
        "email_context": [],
    }

    ctx_factory, _cp = _make_mock_checkpointer()

    with (
        patch("daily.worker.state.AsyncPostgresSaver.from_conn_string", ctx_factory),
        patch("daily.worker.state._resolve_email_adapters", AsyncMock(return_value=[])),
        patch("daily.worker.state.build_graph", return_value=object()),
        patch("daily.worker.state.Redis.from_url", return_value=_make_mock_redis()),
        patch("daily.worker.state.initialize_session_state", AsyncMock(return_value=fake_initial_state)),
        patch("daily.worker.state.set_email_adapters"),
    ):
        from daily.config import Settings

        settings = Settings(
            database_url="postgresql+asyncpg://test/test",
            database_url_psycopg="postgresql+psycopg://test/test",
            redis_url="redis://localhost",
            openai_api_key="sk-test",
            vault_key="",
        )

        async with load_user_session_state(user_id=1, settings=settings) as bundle:
            thread_id = bundle.config["configurable"]["thread_id"]
            assert re.match(r"^user-1-\d{4}-\d{2}-\d{2}$", thread_id), (
                f"thread_id '{thread_id}' does not match user-1-YYYY-MM-DD"
            )


@pytest.mark.asyncio
async def test_briefing_empty_on_cache_miss(monkeypatch):
    """When initialize_session_state returns briefing_narrative='', bundle.briefing_narrative is ''."""
    from daily.worker.state import load_user_session_state

    fake_initial_state = {
        "briefing_narrative": "",
        "active_user_id": 1,
        "preferences": {},
        "email_context": [],
    }

    ctx_factory, _cp = _make_mock_checkpointer()

    with (
        patch("daily.worker.state.AsyncPostgresSaver.from_conn_string", ctx_factory),
        patch("daily.worker.state._resolve_email_adapters", AsyncMock(return_value=[])),
        patch("daily.worker.state.build_graph", return_value=object()),
        patch("daily.worker.state.Redis.from_url", return_value=_make_mock_redis()),
        patch("daily.worker.state.initialize_session_state", AsyncMock(return_value=fake_initial_state)),
        patch("daily.worker.state.set_email_adapters"),
    ):
        from daily.config import Settings

        settings = Settings(
            database_url="postgresql+asyncpg://test/test",
            database_url_psycopg="postgresql+psycopg://test/test",
            redis_url="redis://localhost",
            openai_api_key="sk-test",
            vault_key="",
        )

        async with load_user_session_state(user_id=1, settings=settings) as bundle:
            assert bundle.briefing_narrative == ""
