"""Integration router tests: GET /integrations/* OAuth endpoints (Plan 21-03).

Tests cover INT-01 through INT-07 plus the auth gate check.

Strategy:
- In-memory SQLite for DB (avoids PostgreSQL ARRAY type — only creates tables used here)
- fakeredis for Redis (no live Redis needed)
- Monkeypatched Google Flow.fetch_token and MSAL acquire_token_by_authorization_code
- respx for mocking async httpx POST to Slack
"""
import base64
import os
from unittest.mock import MagicMock, patch

import pytest
import respx
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from daily.db.models import Base, IntegrationToken, User


# ---------------------------------------------------------------------------
# Environment setup — deterministic secrets for tests
# ---------------------------------------------------------------------------

JWT_SECRET = "x" * 32
# Standard base64 encoding of 32 raw bytes — decodes to exactly 32 bytes via
# the canonical load_vault_key() decoder (CRIT-02 fix). Previously this was
# the raw ASCII string "y" * 32, which relied on _vault_key()'s now-removed
# raw-bytes fallback (32 ASCII chars is NOT valid base64 for 32 bytes — it
# decodes to 24 bytes and would now raise ValueError).
VAULT_KEY = base64.b64encode(b"y" * 32).decode()


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("VAULT_KEY", VAULT_KEY)
    monkeypatch.setenv("MAGIC_LINK_BASE_URL", "https://app.example.com")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "fake-google-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "fake-google-secret")
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "fake-ms-id")
    monkeypatch.setenv("MICROSOFT_TENANT_ID", "fake-tenant")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "fake-ms-secret")
    monkeypatch.setenv("SLACK_CLIENT_ID", "fake-slack-id")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "fake-slack-secret")


# ---------------------------------------------------------------------------
# DB fixture — SQLite in-memory, only relevant tables
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
            tables=[User.__table__, IntegrationToken.__table__],
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


# ---------------------------------------------------------------------------
# Redis fixture — fakeredis
# ---------------------------------------------------------------------------


@pytest.fixture
async def fake_redis():
    import fakeredis.aioredis as fake_aioredis

    client = fake_aioredis.FakeRedis()
    yield client
    await client.aclose()


# ---------------------------------------------------------------------------
# Test user seed
# ---------------------------------------------------------------------------


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
# FastAPI test client with patched DB, Redis, and async_session
# ---------------------------------------------------------------------------


@pytest.fixture
async def client(db_factory, fake_redis, test_user, monkeypatch):
    import daily.auth.deps as deps_module
    import daily.auth.router as auth_router_module
    import daily.integrations.router as integrations_module

    monkeypatch.setattr(auth_router_module, "async_session", db_factory)
    monkeypatch.setattr(deps_module, "async_session", db_factory)
    monkeypatch.setattr(integrations_module, "async_session", db_factory)

    # Override _get_redis dependency to use fake_redis
    from daily.integrations.router import router as integrations_router

    async def _fake_get_redis():
        yield fake_redis

    integrations_router.dependency_overrides = {}  # reset
    from daily.main import app

    app.dependency_overrides[integrations_module._get_redis] = _fake_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, fake_redis, db_factory

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# INT-01: GET /integrations/google/connect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_google_connect(client, auth_headers):
    """INT-01: Authenticated connect returns 200 with auth_url; state stored in Redis."""
    ac, redis, _ = client

    response = await ac.get("/integrations/google/connect", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert "auth_url" in body
    assert "accounts.google.com/o/oauth2/auth" in body["auth_url"]

    # Verify Redis contains an oauth_state:{...} key for user_id=100
    keys = await redis.keys("oauth_state:*")
    assert len(keys) == 1
    state_val = await redis.get(keys[0])
    assert state_val is not None
    assert state_val.decode() == "100"

    # Verify TTL is set (≤ 600 seconds)
    ttl = await redis.ttl(keys[0])
    assert 0 < ttl <= 600


# ---------------------------------------------------------------------------
# INT-02: GET /integrations/google/callback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_google_callback(client, auth_headers):
    """INT-02: Callback exchanges code, stores IntegrationToken(provider='google'), 302."""
    ac, redis, db_factory = client

    # Pre-populate state in Redis as if connect was called
    state = "test-google-state-abc123"
    await redis.setex(f"oauth_state:{state}", 600, "100")

    # Build a mock credentials object
    mock_creds = MagicMock()
    mock_creds.token = "fake-access-token"
    mock_creds.refresh_token = "fake-refresh-token"
    mock_creds.expiry = None
    mock_creds.scopes = ["https://www.googleapis.com/auth/gmail.readonly"]

    mock_flow = MagicMock()
    mock_flow.credentials = mock_creds
    mock_flow.authorization_url.return_value = ("https://accounts.google.com/o/oauth2/auth?...", state)

    with patch("daily.integrations.router.Flow") as MockFlow:
        MockFlow.from_client_config.return_value = mock_flow

        response = await ac.get(
            f"/integrations/google/callback?code=fake-code&state={state}",
            follow_redirects=False,
        )

    assert response.status_code == 302
    location = response.headers["location"]
    assert "/oauth/success?provider=google" in location

    # State should be deleted from Redis
    remaining = await redis.get(f"oauth_state:{state}")
    assert remaining is None

    # IntegrationToken row should exist
    async with db_factory() as s:
        from sqlalchemy import select
        rows = (await s.execute(
            select(IntegrationToken).where(
                IntegrationToken.user_id == 100,
                IntegrationToken.provider == "google",
            )
        )).scalars().all()
    assert len(rows) == 1
    assert rows[0].encrypted_access_token  # not empty / not plaintext


# ---------------------------------------------------------------------------
# INT-07: Invalid state returns 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_state(client):
    """INT-07: Callback with state not in Redis returns HTTP 400."""
    ac, _, _ = client

    response = await ac.get(
        "/integrations/google/callback?code=fake&state=nonexistent-state",
        follow_redirects=False,
    )

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Auth gate: unauthenticated request returns 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_requires_auth(client):
    """GET /integrations/google/connect without Bearer token returns HTTP 401."""
    ac, _, _ = client

    response = await ac.get("/integrations/google/connect")

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# INT-03: GET /integrations/microsoft/connect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_microsoft_connect(client, auth_headers):
    """INT-03: Authenticated connect returns 200 with Microsoft auth_url."""
    ac, redis, _ = client

    mock_msal_app = MagicMock()
    mock_msal_app.get_authorization_request_url.return_value = (
        "https://login.microsoftonline.com/fake-tenant/oauth2/v2.0/authorize?client_id=fake"
    )

    with patch("daily.integrations.router.msal.ConfidentialClientApplication", return_value=mock_msal_app):
        response = await ac.get("/integrations/microsoft/connect", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert "auth_url" in body
    assert "login.microsoftonline.com" in body["auth_url"]


# ---------------------------------------------------------------------------
# INT-04: GET /integrations/microsoft/callback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_microsoft_callback(client, auth_headers):
    """INT-04: Callback stores IntegrationToken(provider='outlook'), returns 302."""
    ac, redis, db_factory = client

    state = "test-ms-state-xyz"
    await redis.setex(f"oauth_state:{state}", 600, "100")

    mock_msal_app = MagicMock()
    mock_msal_app.acquire_token_by_authorization_code.return_value = {
        "access_token": "ms-access-token",
        "refresh_token": "ms-refresh-token",
        "expires_in": 3600,
    }

    with patch("daily.integrations.router.msal.ConfidentialClientApplication", return_value=mock_msal_app):
        response = await ac.get(
            f"/integrations/microsoft/callback?code=fake-code&state={state}",
            follow_redirects=False,
        )

    assert response.status_code == 302
    location = response.headers["location"]
    assert "/oauth/success?provider=microsoft" in location

    # Must store as provider="outlook" (NOT "microsoft")
    async with db_factory() as s:
        from sqlalchemy import select
        rows = (await s.execute(
            select(IntegrationToken).where(
                IntegrationToken.user_id == 100,
                IntegrationToken.provider == "outlook",
            )
        )).scalars().all()
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# INT-05: GET /integrations/slack/connect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slack_connect(client, auth_headers):
    """INT-05: Authenticated connect returns 200 with Slack auth_url."""
    ac, _, _ = client

    response = await ac.get("/integrations/slack/connect", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert "auth_url" in body
    assert "slack.com/oauth/v2/authorize" in body["auth_url"]


# ---------------------------------------------------------------------------
# Audit C3/H7: blocking OAuth code-exchange calls run off the event loop
# with a timeout, so a slow/hanging IdP can't stall the whole process.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_blocking_token_exchange_returns_value():
    """_run_blocking_token_exchange runs a sync callable via to_thread and returns its result."""
    from daily.integrations.router import _run_blocking_token_exchange

    def sync_fn(a, b, kw=None):
        return {"a": a, "b": b, "kw": kw}

    result = await _run_blocking_token_exchange(sync_fn, 1, 2, kw="three")
    assert result == {"a": 1, "b": 2, "kw": "three"}


@pytest.mark.asyncio
async def test_run_blocking_token_exchange_raises_504_on_timeout():
    """A code-exchange call that never returns in time raises HTTPException 504, not a hang."""
    import time

    from fastapi import HTTPException

    from daily.integrations.router import _run_blocking_token_exchange

    with patch(
        "daily.integrations.router.OAUTH_TOKEN_EXCHANGE_TIMEOUT_SECONDS", 0.05
    ):
        def slow_fn():
            time.sleep(1)
            return "too late"

        with pytest.raises(HTTPException) as exc:
            await _run_blocking_token_exchange(slow_fn)

    assert exc.value.status_code == 504


@pytest.mark.asyncio
async def test_google_callback_wraps_fetch_token_in_to_thread(client, auth_headers):
    """google_callback calls flow.fetch_token via _run_blocking_token_exchange (asyncio.to_thread)."""
    ac, redis, _ = client

    state = "test-google-state-tothread"
    await redis.setex(f"oauth_state:{state}", 600, "100")

    mock_creds = MagicMock()
    mock_creds.token = "fake-access-token"
    mock_creds.refresh_token = "fake-refresh-token"
    mock_creds.expiry = None
    mock_creds.scopes = ["https://www.googleapis.com/auth/gmail.readonly"]

    mock_flow = MagicMock()
    mock_flow.credentials = mock_creds

    with patch("daily.integrations.router.Flow") as MockFlow:
        MockFlow.from_client_config.return_value = mock_flow

        response = await ac.get(
            f"/integrations/google/callback?code=fake-code&state={state}",
            follow_redirects=False,
        )

    assert response.status_code == 302
    mock_flow.fetch_token.assert_called_once()


# ---------------------------------------------------------------------------
# INT-06: GET /integrations/slack/callback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slack_callback(client, auth_headers):
    """INT-06: Slack callback exchanges code via httpx; stores provider='slack'."""
    ac, redis, db_factory = client

    state = "test-slack-state-lmn"
    await redis.setex(f"oauth_state:{state}", 600, "100")

    with respx.mock:
        respx.post("https://slack.com/api/oauth.v2.access").mock(
            return_value=Response(
                200,
                json={"ok": True, "access_token": "xoxb-fake-bot-token"},
            )
        )

        response = await ac.get(
            f"/integrations/slack/callback?code=fake-code&state={state}",
            follow_redirects=False,
        )

    assert response.status_code == 302
    location = response.headers["location"]
    assert "/oauth/success?provider=slack" in location

    # Must store as provider="slack"
    async with db_factory() as s:
        from sqlalchemy import select
        rows = (await s.execute(
            select(IntegrationToken).where(
                IntegrationToken.user_id == 100,
                IntegrationToken.provider == "slack",
            )
        )).scalars().all()
    assert len(rows) == 1
