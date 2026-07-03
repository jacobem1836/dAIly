"""Phase 18 INFRA-02: pairing + refresh integration tests.

Uses SQLite in-memory database to test the auth endpoints end-to-end without
requiring a live PostgreSQL instance.

NOTE (security fix, wave 1 audit remediation): POST /auth/pair/initiate was
removed — it let anyone auto-create a user and mint a valid pairing code for
an arbitrary user_id with zero auth (unauthenticated account takeover). It
was unused by the iOS app (the real flow is /auth/pair/send-link, a magic
link). These tests now seed PairingCode rows directly via the DB session,
mirroring how the magic-link flow already does this in
test_auth_router_coverage.py.
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from daily.auth.pairing import code_expiry, generate_pairing_code
from daily.db.models import Base, PairingCode, User


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    import base64
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    # VAULT_KEY is base64-encoded by auth/router.py before use — must decode to 32 bytes
    monkeypatch.setenv("VAULT_KEY", base64.b64encode(b"y" * 32).decode())


@pytest.fixture
async def db_session_factory():
    """Create an in-memory SQLite session factory for tests.

    Only creates the tables needed for auth tests (avoids SQLite ARRAY type
    incompatibility in BriefingConfig.slack_channels).
    """
    from daily.db.models import User, PairingCode, DeviceToken

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        # Create only the tables needed for auth tests
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


async def _seed_pairing_code(db_session_factory, user_id: int) -> str:
    """Create a User + an unused, unexpired PairingCode row for that user.

    Replaces the deleted /auth/pair/initiate endpoint for test setup.
    """
    code = generate_pairing_code()
    async with db_session_factory() as session:
        user = await session.get(User, user_id)
        if user is None:
            session.add(User(id=user_id))
        session.add(PairingCode(user_id=user_id, code=code, expires_at=code_expiry()))
        await session.commit()
    return code


@pytest.fixture
async def client(db_session_factory, mock_redis, monkeypatch):
    """FastAPI test client with mocked DB session using in-memory SQLite.

    Also overrides the rate limiter's Redis dependency with fakeredis
    (mock_redis, from tests/conftest.py) so these tests don't need a live
    Redis instance.
    """
    import daily.auth.deps as deps_module
    import daily.auth.ratelimit as ratelimit_module
    import daily.auth.router as auth_router_module

    # Patch the async_session in auth router and deps to use our test DB
    monkeypatch.setattr(auth_router_module, "async_session", db_session_factory)
    monkeypatch.setattr(deps_module, "async_session", db_session_factory)

    from daily.main import app

    async def _fake_get_redis():
        yield mock_redis

    app.dependency_overrides[ratelimit_module.get_redis] = _fake_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, db_session_factory

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_full_pairing_flow(client):
    ac, db_factory = client
    code = await _seed_pairing_code(db_factory, user_id=1)
    assert len(code) == 6 and code.isdigit()

    r2 = await ac.post("/auth/pair/complete", json={"code": code, "device_name": "test"})
    assert r2.status_code == 200
    body = r2.json()
    assert body["access_token"] and body["refresh_token"]


@pytest.mark.asyncio
async def test_invalid_code_rejected(client):
    ac, _ = client
    r = await ac.post("/auth/pair/complete", json={"code": "000000"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_used_code_rejected(client):
    ac, db_factory = client
    code = await _seed_pairing_code(db_factory, user_id=2)
    r1 = await ac.post("/auth/pair/complete", json={"code": code})
    assert r1.status_code == 200
    r2 = await ac.post("/auth/pair/complete", json={"code": code})
    assert r2.status_code == 400


@pytest.mark.asyncio
async def test_refresh_token_exchange(client):
    ac, db_factory = client
    code = await _seed_pairing_code(db_factory, user_id=3)
    r1 = await ac.post("/auth/pair/complete", json={"code": code})
    refresh = r1.json()["refresh_token"]
    r2 = await ac.post("/auth/token/refresh", json={"refresh_token": refresh})
    assert r2.status_code == 200
    assert r2.json()["access_token"]


@pytest.mark.asyncio
async def test_invalid_refresh_token_rejected(client):
    ac, _ = client
    r = await ac.post("/auth/token/refresh", json={"refresh_token": "not-a-real-token"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_stored_encrypted(client):
    """Plaintext refresh token must NOT appear in the device_tokens table."""
    from sqlalchemy import select
    from daily.db.models import DeviceToken

    ac, db_factory = client
    code = await _seed_pairing_code(db_factory, user_id=4)
    r1 = await ac.post("/auth/pair/complete", json={"code": code})
    refresh = r1.json()["refresh_token"]

    async with db_factory() as s:
        result = await s.execute(select(DeviceToken).where(DeviceToken.user_id == 4))
        rows = list(result.scalars())
        assert rows, "DeviceToken row not created"
        for dt in rows:
            assert dt.encrypted_refresh_token != refresh, "Refresh token stored plaintext!"


@pytest.mark.asyncio
async def test_pair_complete_rate_limited_after_threshold(client):
    """20 requests/5min limit on /auth/pair/complete — the 21st must 429.

    Security fix, wave 1: this endpoint guards a brute-forceable 6-digit
    code (900k values) and previously had no rate limiting at all.
    """
    ac, _ = client
    responses = [
        await ac.post("/auth/pair/complete", json={"code": "000000"}) for _ in range(21)
    ]
    assert responses[-1].status_code == 429
    assert all(r.status_code == 400 for r in responses[:20])


@pytest.mark.asyncio
async def test_pair_send_link_rate_limited_after_threshold(client):
    """10 requests/min limit on /auth/pair/send-link — the 11th must 429."""
    ac, _ = client
    responses = [
        await ac.post("/auth/pair/send-link", json={"email": "flood@example.com"})
        for _ in range(11)
    ]
    assert responses[-1].status_code == 429


@pytest.mark.asyncio
async def test_failed_attempts_invalidate_pending_codes(client):
    """After 5 failed pair/complete guesses from one client, pending codes die.

    Security fix, wave 1: defense-in-depth beyond generic rate limiting —
    a sustained wrong-guess streak burns down currently pending pairing
    codes rather than leaving them guessable for the rest of the window.
    """
    ac, db_factory = client
    code = await _seed_pairing_code(db_factory, user_id=5)

    for _ in range(5):
        r = await ac.post("/auth/pair/complete", json={"code": "999999"})
        assert r.status_code == 400

    # The legitimately-issued code must now be invalidated too.
    r = await ac.post("/auth/pair/complete", json={"code": code})
    assert r.status_code == 400
