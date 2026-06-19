"""Phase 18 INFRA-02: pairing + refresh integration tests.

Uses SQLite in-memory database to test the auth endpoints end-to-end without
requiring a live PostgreSQL instance.
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from daily.db.models import Base


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


@pytest.fixture
async def client(db_session_factory, monkeypatch):
    """FastAPI test client with mocked DB session using in-memory SQLite."""
    import daily.auth.router as auth_router_module
    import daily.auth.deps as deps_module

    # Patch the async_session in auth router and deps to use our test DB
    monkeypatch.setattr(auth_router_module, "async_session", db_session_factory)
    monkeypatch.setattr(deps_module, "async_session", db_session_factory)

    from daily.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, db_session_factory


@pytest.mark.asyncio
async def test_full_pairing_flow(client):
    ac, _ = client
    r = await ac.post("/auth/pair/initiate", json={"user_id": 1})
    assert r.status_code == 200
    code = r.json()["code"]
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
    ac, _ = client
    r = await ac.post("/auth/pair/initiate", json={"user_id": 2})
    code = r.json()["code"]
    r1 = await ac.post("/auth/pair/complete", json={"code": code})
    assert r1.status_code == 200
    r2 = await ac.post("/auth/pair/complete", json={"code": code})
    assert r2.status_code == 400


@pytest.mark.asyncio
async def test_refresh_token_exchange(client):
    ac, _ = client
    r = await ac.post("/auth/pair/initiate", json={"user_id": 3})
    code = r.json()["code"]
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
    r = await ac.post("/auth/pair/initiate", json={"user_id": 4})
    code = r.json()["code"]
    r1 = await ac.post("/auth/pair/complete", json={"code": code})
    refresh = r1.json()["refresh_token"]

    async with db_factory() as s:
        result = await s.execute(select(DeviceToken).where(DeviceToken.user_id == 4))
        rows = list(result.scalars())
        assert rows, "DeviceToken row not created"
        for dt in rows:
            assert dt.encrypted_refresh_token != refresh, "Refresh token stored plaintext!"
