"""Tests for GET /users/me/integrations and PUT /users/me/preferences (Plan 21-04).

Uses SQLite in-memory database + FastAPI TestClient pattern from test_livekit_token.py.
Covers USR-01, USR-02, USR-03 from 21-RESEARCH.md.
"""
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from daily.auth.jwt import encode_access_token
from daily.config import Settings
from daily.db.models import Base


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("LIVEKIT_API_KEY", "test-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "test-secret-32-bytes-padded-x")
    monkeypatch.setenv("LIVEKIT_URL", "ws://localhost:7880")
    monkeypatch.setenv("VAULT_KEY", "y" * 32)


@pytest.fixture
async def db_session_factory():
    """In-memory SQLite engine with user-relevant tables.

    BriefingConfig uses PostgreSQL ARRAY for slack_channels which SQLite does not
    support. We register a SQLAlchemy event listener that serialises Python lists
    to JSON strings before INSERT/UPDATE so SQLite can store them as TEXT.
    The table is created via raw DDL with a TEXT column for slack_channels.
    """
    import json

    import sqlalchemy.event as sa_event
    from daily.db.models import IntegrationToken, User

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    # Adapt Python list → JSON string for SQLite (slack_channels ARRAY workaround)
    @sa_event.listens_for(engine.sync_engine, "before_cursor_execute", retval=True)
    def adapt_array_params(conn, cursor, statement, parameters, context, executemany):
        if parameters and isinstance(parameters, (list, tuple)):
            adapted = []
            for p in parameters:
                if isinstance(p, list):
                    adapted.append(json.dumps(p))
                else:
                    adapted.append(p)
            return statement, tuple(adapted)
        return statement, parameters

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                User.__table__,
                IntegrationToken.__table__,
            ],
        )
        # Create briefing_config with SQLite-compatible TEXT for slack_channels
        await conn.execute(
            __import__("sqlalchemy", fromlist=["text"]).text(
                """
                CREATE TABLE briefing_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
                    schedule_hour INTEGER NOT NULL DEFAULT 5,
                    schedule_minute INTEGER NOT NULL DEFAULT 0,
                    timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
                    email_top_n INTEGER NOT NULL DEFAULT 5,
                    slack_channels TEXT NOT NULL DEFAULT '{}',
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def client(db_session_factory, monkeypatch):
    """FastAPI test client with SQLite session injected into deps."""
    import daily.auth.deps as deps_module
    import daily.users.router as users_router_module

    monkeypatch.setattr(deps_module, "async_session", db_session_factory)
    monkeypatch.setattr(users_router_module, "async_session", db_session_factory)

    from daily.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, db_session_factory


@pytest.fixture
async def auth_user(db_session_factory):
    """Ensure user 100 exists in SQLite DB. Returns user_id."""
    from daily.db.models import User

    async with db_session_factory() as s:
        u = await s.get(User, 100)
        if u is None:
            u = User(id=100)
            s.add(u)
            await s.commit()
    return 100


def _bearer(user_id: int) -> dict[str, str]:
    settings = Settings()
    token = encode_access_token(user_id=user_id, settings=settings)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# USR-01: GET /users/me/integrations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_integration_status(client, auth_user):
    """USR-01: GET /users/me/integrations returns correct boolean map.

    With google + outlook tokens, slack absent:
    - google: true, microsoft: true (outlook→microsoft mapping), slack: false
    """
    from daily.db.models import IntegrationToken

    ac, db = client

    # Insert integration tokens for the test user
    async with db() as s:
        s.add(
            IntegrationToken(
                user_id=auth_user,
                provider="google",
                encrypted_access_token="enc_google",
                scopes="read",
            )
        )
        s.add(
            IntegrationToken(
                user_id=auth_user,
                provider="outlook",
                encrypted_access_token="enc_outlook",
                scopes="read",
            )
        )
        await s.commit()

    r = await ac.get("/users/me/integrations", headers=_bearer(auth_user))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"google": True, "microsoft": True, "slack": False}


@pytest.mark.asyncio
async def test_integration_status_no_auth(client):
    """GET /users/me/integrations without Bearer token returns 401."""
    ac, _ = client
    r = await ac.get("/users/me/integrations")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# USR-02: PUT /users/me/preferences
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_preferences(client, auth_user):
    """USR-02: PUT /users/me/preferences upserts BriefingConfig with UTC conversion.

    07:00 Australia/Brisbane (UTC+10, no DST) => 21:00 UTC previous logical day,
    i.e., utc_hour=21, utc_minute=0.  Use ZoneInfo to compute expected values
    in the test so the assertion is DST-correct regardless of test run date.
    """
    from daily.db.models import BriefingConfig

    ac, db = client

    tz_name = "Australia/Brisbane"
    local_time = "07:00"

    # Compute expected UTC values the same way the endpoint does
    from datetime import datetime, timezone as _tz

    tz = ZoneInfo(tz_name)
    h, m = 7, 0
    local_now = datetime.now(tz).replace(hour=h, minute=m, second=0, microsecond=0)
    utc = local_now.astimezone(_tz.utc)
    expected_hour = utc.hour
    expected_minute = utc.minute

    r = await ac.put(
        "/users/me/preferences",
        json={"briefing_time": local_time, "timezone": tz_name},
        headers=_bearer(auth_user),
    )
    assert r.status_code == 204, r.text

    # Verify DB row
    async with db() as s:
        result = await s.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(BriefingConfig).where(
                BriefingConfig.user_id == auth_user
            )
        )
        config = result.scalar_one()
        assert config.schedule_hour == expected_hour
        assert config.schedule_minute == expected_minute
        assert config.timezone == tz_name

    # Second PUT with different time — should upsert (no duplicate row)
    r2 = await ac.put(
        "/users/me/preferences",
        json={"briefing_time": "08:00", "timezone": tz_name},
        headers=_bearer(auth_user),
    )
    assert r2.status_code == 204, r2.text

    async with db() as s:
        from sqlalchemy import func, select as sa_select

        count_result = await s.execute(
            sa_select(func.count()).select_from(BriefingConfig).where(
                BriefingConfig.user_id == auth_user
            )
        )
        assert count_result.scalar() == 1, "Expected exactly one BriefingConfig row (upsert)"


@pytest.mark.asyncio
async def test_update_preferences_no_auth(client):
    """PUT /users/me/preferences without Bearer token returns 401."""
    ac, _ = client
    r = await ac.put(
        "/users/me/preferences",
        json={"briefing_time": "07:00", "timezone": "Australia/Brisbane"},
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# USR-03: PUT /users/me/preferences — invalid timezone
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_timezone(client, auth_user):
    """USR-03: PUT /users/me/preferences with invalid timezone returns 422."""
    ac, _ = client
    r = await ac.put(
        "/users/me/preferences",
        json={"briefing_time": "07:00", "timezone": "Not/A_Zone"},
        headers=_bearer(auth_user),
    )
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# PreferencesUpdateRequest validator branches
# ---------------------------------------------------------------------------


def test_validate_time_missing_colon():
    """Validator raises on briefing_time without colon (line 72)."""
    import pytest
    from pydantic import ValidationError
    from daily.users.router import PreferencesUpdateRequest

    with pytest.raises(ValidationError) as exc_info:
        PreferencesUpdateRequest(briefing_time="700", timezone="UTC")
    assert "HH:MM" in str(exc_info.value)


def test_validate_time_non_integer_parts():
    """Validator raises when hour/minute are not integers (lines 75-76)."""
    import pytest
    from pydantic import ValidationError
    from daily.users.router import PreferencesUpdateRequest

    with pytest.raises(ValidationError) as exc_info:
        PreferencesUpdateRequest(briefing_time="ab:cd", timezone="UTC")
    assert "integer" in str(exc_info.value)


def test_validate_time_out_of_range():
    """Validator raises when hour > 23 or minute > 59 (line 78)."""
    import pytest
    from pydantic import ValidationError
    from daily.users.router import PreferencesUpdateRequest

    with pytest.raises(ValidationError) as exc_info:
        PreferencesUpdateRequest(briefing_time="25:00", timezone="UTC")
    assert "0-23" in str(exc_info.value)


def test_validate_time_valid():
    """Validator accepts a well-formed HH:MM string."""
    from daily.users.router import PreferencesUpdateRequest

    req = PreferencesUpdateRequest(briefing_time="07:30", timezone="UTC")
    assert req.briefing_time == "07:30"
