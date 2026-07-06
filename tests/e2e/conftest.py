"""E2E test fixtures for dAIly smoke tests.

Uses in-memory SQLite for the full schema with one workaround:
- BriefingConfig.slack_channels uses ARRAY(String) which SQLite does not support.
  We register a SQLAlchemy TypeDecorator (JsonList) that serialises Python lists to
  JSON strings and back, then patch BriefingConfig.slack_channels to use JsonList
  before creating the SQLite engine. This is a DDL+DML compatibility shim for tests
  only; the production column type remains ARRAY(String) on PostgreSQL.

Fixtures:
  engine         - in-memory SQLite async engine with full Base.metadata schema
  db_factory     - async_sessionmaker bound to engine
  client         - httpx.AsyncClient via ASGITransport against full FastAPI app,
                   with async_session monkeypatched in all router and deps modules
  mock_resend    - records send_magic_link calls without making HTTP requests
  mock_oauth_exchange - pre-populates Redis state and makes Google Flow mock available
"""
import base64
import json
from unittest.mock import MagicMock, patch

import fakeredis.aioredis as fake_aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import String, Text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.types import TypeDecorator

from daily.db.models import Base, BriefingConfig
from daily.profile.models import UserProfile
from daily.profile.signals import SignalLog


# ---------------------------------------------------------------------------
# SQLite ARRAY/JSONB compatibility shims
# Replace PostgreSQL-specific column types with TEXT-backed equivalents.
# ---------------------------------------------------------------------------


class _JsonList(TypeDecorator):
    """Store Python list as a JSON string in SQLite TEXT column.

    On PostgreSQL (production) the real ARRAY(String) type is used instead.
    This TypeDecorator is only registered here in the E2E test fixtures.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: ANN001, ANN201
        if value is None:
            return "[]"
        return json.dumps(value)

    def process_result_value(self, value, dialect):  # noqa: ANN001, ANN201
        if value is None:
            return []
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return []


class _JsonB(TypeDecorator):
    """Store Python dict as a JSON string in SQLite TEXT column.

    On PostgreSQL (production) the real JSONB type is used instead.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: ANN001, ANN201
        if value is None:
            return None
        return json.dumps(value)

    def process_result_value(self, value, dialect):  # noqa: ANN001, ANN201
        if value is None:
            return None
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return {}


# Patch PostgreSQL-specific column types before any engine creates the schema.
BriefingConfig.__table__.c["slack_channels"].type = _JsonList()
UserProfile.__table__.c["preferences"].type = _JsonB()
SignalLog.__table__.c["metadata_json"].type = _JsonB()


# ---------------------------------------------------------------------------
# Environment setup
# ---------------------------------------------------------------------------

JWT_SECRET = "x" * 32
# VAULT_KEY must base64-decode to exactly 32 bytes (used by auth/router.py)
VAULT_KEY = base64.b64encode(b"y" * 32).decode()


@pytest.fixture(autouse=True)
def _e2e_env(monkeypatch):
    """Set all required environment variables for the E2E test suite."""
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("VAULT_KEY", VAULT_KEY)
    monkeypatch.setenv("RESEND_API_KEY", "test-resend-key")
    monkeypatch.setenv("MAGIC_LINK_BASE_URL", "https://app.example.com")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "fake-google-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "fake-google-secret")
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "fake-ms-id")
    monkeypatch.setenv("MICROSOFT_TENANT_ID", "fake-tenant")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "fake-ms-secret")
    monkeypatch.setenv("SLACK_CLIENT_ID", "fake-slack-id")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "fake-slack-secret")
    # Settings() now rejects LiveKit's known-public quickstart devkey/secret
    # pair at startup (security fix, wave 1 audit remediation) — use
    # non-blocklisted test values instead.
    monkeypatch.setenv("LIVEKIT_API_KEY", "test-e2e-livekit-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "test-e2e-livekit-secret-32chars")
    monkeypatch.setenv("LIVEKIT_URL", "ws://localhost:7880")


# ---------------------------------------------------------------------------
# engine — in-memory SQLite with full schema
# ---------------------------------------------------------------------------


@pytest.fixture
async def engine():
    """In-memory SQLite async engine with the full Base.metadata schema.

    The ARRAY(String) type in BriefingConfig.slack_channels is handled by the
    _compile_array_sqlite compiles extension above, rendering it as TEXT.
    """
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


# ---------------------------------------------------------------------------
# db_factory — session factory bound to engine
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_factory(engine):
    """Async session factory bound to the in-memory SQLite engine."""
    yield async_sessionmaker(engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# fake_redis — fakeredis instance for OAuth state storage
# ---------------------------------------------------------------------------


@pytest.fixture
async def _fake_redis():
    client = fake_aioredis.FakeRedis()
    yield client
    await client.aclose()


# ---------------------------------------------------------------------------
# client — full FastAPI app via ASGITransport with patched DB and Redis
# ---------------------------------------------------------------------------


@pytest.fixture
async def client(db_factory, _fake_redis, monkeypatch):
    """AsyncClient using ASGITransport against the full FastAPI app.

    Patches async_session in every module that imports it so all routers and
    deps use the in-memory SQLite DB. Redis dependency is overridden via
    app.dependency_overrides.
    """
    import daily.auth.deps as deps_module
    import daily.auth.router as auth_router_module
    import daily.integrations.router as integrations_module
    import daily.users.router as users_router_module

    monkeypatch.setattr(auth_router_module, "async_session", db_factory)
    monkeypatch.setattr(deps_module, "async_session", db_factory)
    monkeypatch.setattr(integrations_module, "async_session", db_factory)
    monkeypatch.setattr(users_router_module, "async_session", db_factory)

    async def _fake_get_redis():
        yield _fake_redis

    from daily.main import app

    app.dependency_overrides[integrations_module._get_redis] = _fake_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, _fake_redis, db_factory

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# mock_resend — captures send_magic_link calls without HTTP
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_resend():
    """Mock send_magic_link to record calls without making real HTTP requests.

    Yields a list that is populated with (email, code) tuples for each call.
    """
    calls: list[tuple[str, str]] = []

    async def _fake_send(email: str, code: str, *, settings) -> None:  # noqa: ANN001
        calls.append((email, code))

    with patch("daily.auth.router.send_magic_link", side_effect=_fake_send):
        yield calls


# ---------------------------------------------------------------------------
# mock_oauth_exchange — patches Google Flow for callback step
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_oauth_exchange():
    """Patch Google OAuth Flow.fetch_token so the callback step succeeds.

    Yields the mock Flow instance so tests can inspect calls if needed.
    The mock credentials return a fake access_token and refresh_token.
    """
    mock_creds = MagicMock()
    mock_creds.token = "fake-google-access-token"
    mock_creds.refresh_token = "fake-google-refresh-token"
    mock_creds.expiry = None
    mock_creds.scopes = ["https://www.googleapis.com/auth/gmail.readonly"]

    mock_flow = MagicMock()
    mock_flow.credentials = mock_creds
    mock_flow.fetch_token = MagicMock()
    # authorization_url must return a (url, state) tuple
    mock_flow.authorization_url.return_value = (
        "https://accounts.google.com/o/oauth2/auth?fake=1",
        "fake-state",
    )

    with patch("daily.integrations.router.Flow") as MockFlow:
        MockFlow.from_client_config.return_value = mock_flow
        yield mock_flow
