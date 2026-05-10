"""Tests for POST /briefings/trigger endpoint (D-04, Plan 21.2-01 Task 1).

Covers:
 - Authenticated POST returns 202 with {"status": "completed"}
 - Unauthenticated POST returns 401
 - Endpoint calls run_briefing_pipeline with kwargs from _build_pipeline_kwargs
 - Pipeline failure surfaces as 500 with sanitised error (no token data leaked)
"""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from daily.db.models import Base, User


# ---------------------------------------------------------------------------
# Environment setup
# ---------------------------------------------------------------------------

JWT_SECRET = "x" * 32
VAULT_KEY = "y" * 32


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("VAULT_KEY", VAULT_KEY)
    monkeypatch.setenv("MAGIC_LINK_BASE_URL", "https://app.example.com")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "fake-gid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "fake-gsecret")
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "fake-ms-id")
    monkeypatch.setenv("MICROSOFT_TENANT_ID", "fake-tenant")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "fake-ms-secret")
    monkeypatch.setenv("SLACK_CLIENT_ID", "fake-slack-id")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "fake-slack-secret")
    monkeypatch.setenv("BRIEFING_SCHEDULE_TIME", "05:00")
    monkeypatch.setenv("APPLE_TEAM_ID", "XXXXXXXXXX")
    monkeypatch.setenv("APPLE_BUNDLE_ID", "com.example.dAIly")
    monkeypatch.setenv("ANDROID_SHA256_FINGERPRINT", "AA:BB:CC")
    monkeypatch.setenv("ANDROID_PACKAGE_NAME", "com.example.daily")
    monkeypatch.setenv("LIVEKIT_URL", "wss://livekit.example.com")
    monkeypatch.setenv("LIVEKIT_API_KEY", "fake-lk-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "fake-lk-secret")


# ---------------------------------------------------------------------------
# DB fixture — SQLite in-memory
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[User.__table__],
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def test_user(db_factory):
    async with db_factory() as s:
        user = User(id=100, email="test@example.com")
        s.add(user)
        await s.commit()
    return user


# ---------------------------------------------------------------------------
# Auth headers fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def auth_headers():
    from daily.auth.jwt import encode_access_token
    from daily.config import Settings

    settings = Settings(jwt_secret=JWT_SECRET)
    token = encode_access_token(user_id=100, settings=settings)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# App client fixture with patched dependencies
# ---------------------------------------------------------------------------


@pytest.fixture
async def client(db_factory, test_user, monkeypatch):
    import daily.auth.deps as deps_module
    import daily.auth.router as auth_router_module

    monkeypatch.setattr(auth_router_module, "async_session", db_factory)
    monkeypatch.setattr(deps_module, "async_session", db_factory)

    from daily.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# TRIG-01: Authenticated POST returns 202 with {"status": "completed"}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_briefing_authenticated(client, auth_headers):
    """TRIG-01: Authenticated POST /briefings/trigger returns 202 with completed status."""
    mock_kwargs = {
        "email_adapters": [],
        "calendar_adapters": [],
        "message_adapters": [],
        "vip_senders": frozenset(),
        "user_email": "",
        "top_n": 5,
        "redis": AsyncMock(aclose=AsyncMock()),
        "openai_client": MagicMock(),
        "preferences": None,
    }
    with patch(
        "daily.briefing.router._build_pipeline_kwargs",
        new=AsyncMock(return_value=mock_kwargs),
    ), patch(
        "daily.briefing.router.run_briefing_pipeline",
        new=AsyncMock(return_value=MagicMock()),
    ):
        response = await client.post("/briefings/trigger", headers=auth_headers)

    assert response.status_code == 202
    assert response.json() == {"status": "completed"}


# ---------------------------------------------------------------------------
# TRIG-02: Unauthenticated POST returns 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_briefing_unauthenticated(client):
    """TRIG-02: Unauthenticated POST /briefings/trigger returns 401."""
    response = await client.post("/briefings/trigger")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# TRIG-03: Endpoint calls run_briefing_pipeline with correct kwargs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_briefing_calls_pipeline(client, auth_headers):
    """TRIG-03: Endpoint calls run_briefing_pipeline with kwargs from _build_pipeline_kwargs."""
    mock_kwargs = {
        "email_adapters": [],
        "calendar_adapters": [],
        "message_adapters": [],
        "vip_senders": frozenset(),
        "user_email": "user@example.com",
        "top_n": 5,
        "redis": AsyncMock(aclose=AsyncMock()),
        "openai_client": MagicMock(),
        "preferences": None,
    }
    mock_build = AsyncMock(return_value=mock_kwargs)
    mock_pipeline = AsyncMock(return_value=MagicMock())

    with patch("daily.briefing.router._build_pipeline_kwargs", new=mock_build), patch(
        "daily.briefing.router.run_briefing_pipeline", new=mock_pipeline
    ):
        await client.post("/briefings/trigger", headers=auth_headers)

    # _build_pipeline_kwargs was called with user_id=100
    mock_build.assert_called_once()
    call_args = mock_build.call_args
    assert call_args[0][0] == 100  # user_id positional arg

    # run_briefing_pipeline was called with user_id=100 and the kwargs
    mock_pipeline.assert_called_once()
    pipeline_kwargs = mock_pipeline.call_args[1]
    assert pipeline_kwargs["user_id"] == 100


# ---------------------------------------------------------------------------
# TRIG-04: Pipeline failure surfaces as 500 with sanitised error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_briefing_pipeline_failure_returns_500(client, auth_headers):
    """TRIG-04: Pipeline exception returns 500 with sanitised detail — no token data."""
    mock_kwargs = {
        "email_adapters": [],
        "calendar_adapters": [],
        "message_adapters": [],
        "vip_senders": frozenset(),
        "user_email": "",
        "top_n": 5,
        "redis": AsyncMock(aclose=AsyncMock()),
        "openai_client": MagicMock(),
        "preferences": None,
    }
    sensitive_token = "sk-super-secret-access-token-that-must-not-leak"

    with patch(
        "daily.briefing.router._build_pipeline_kwargs",
        new=AsyncMock(return_value=mock_kwargs),
    ), patch(
        "daily.briefing.router.run_briefing_pipeline",
        new=AsyncMock(side_effect=RuntimeError(f"Pipeline broke: {sensitive_token}")),
    ):
        response = await client.post("/briefings/trigger", headers=auth_headers)

    assert response.status_code == 500
    body = response.json()
    assert "detail" in body
    # Sanitised: no raw token data in the response body
    assert sensitive_token not in body["detail"]
    assert body["detail"] == "briefing_generation_failed"
