"""Phase 18 INFRA-02: /livekit/token integration tests.

Uses SQLite in-memory database to avoid PostgreSQL dependency in CI.
Mirrors the test pattern from test_auth_pairing.py (Phase 18-02).
"""
import re
import pytest
from datetime import datetime, timedelta, timezone
import jwt as pyjwt
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from daily.auth.jwt import encode_access_token
from daily.config import Settings
from daily.db.models import Base


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("LIVEKIT_API_KEY", "test-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "test-secret-32-bytes-padded-x")
    monkeypatch.setenv("LIVEKIT_URL", "ws://localhost:7880")
    monkeypatch.setenv("VAULT_KEY", "y" * 32)


@pytest.fixture
async def db_session_factory():
    """In-memory SQLite session factory. Creates only auth-relevant tables."""
    from daily.db.models import User, PairingCode, DeviceToken

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                User.__table__,
                PairingCode.__table__,
                DeviceToken.__table__,
            ],
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def client(db_session_factory, monkeypatch):
    """FastAPI test client with SQLite-backed session injected into auth deps."""
    import daily.auth.deps as deps_module
    import daily.auth.router as auth_router_module

    monkeypatch.setattr(deps_module, "async_session", db_session_factory)
    monkeypatch.setattr(auth_router_module, "async_session", db_session_factory)

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


@pytest.mark.asyncio
async def test_unauthorized(client):
    ac, _ = client
    r = await ac.post("/livekit/token")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_unauthorized_invalid_token(client):
    ac, _ = client
    r = await ac.post(
        "/livekit/token",
        headers={"Authorization": "Bearer garbage.not.a.jwt"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_unauthorized_expired_token(client):
    ac, _ = client
    settings = Settings()
    expired = pyjwt.encode(
        {
            "sub": "100",
            "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
            "iat": datetime.now(timezone.utc) - timedelta(minutes=1),
            "type": "access",
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    r = await ac.post(
        "/livekit/token",
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_valid_token(client, auth_user):
    ac, _ = client
    settings = Settings()
    access = encode_access_token(auth_user, settings)
    r = await ac.post(
        "/livekit/token",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token"]
    assert re.match(rf"^session-{auth_user}-\d+$", body["room"])
    assert body["livekit_url"] == settings.livekit_url


@pytest.mark.asyncio
async def test_returned_token_signed_with_livekit_secret(client, auth_user):
    ac, _ = client
    settings = Settings()
    access = encode_access_token(auth_user, settings)
    r = await ac.post(
        "/livekit/token",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    payload = pyjwt.decode(
        body["token"],
        settings.livekit_api_secret,
        algorithms=["HS256"],
        options={"verify_aud": False},
    )
    assert payload["sub"] == str(auth_user)
