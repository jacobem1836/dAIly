"""Tests for POST /auth/pair/send-link (Phase 19, Task 2).

Uses SQLite in-memory database + monkeypatch on send_magic_link.
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from daily.db.models import Base, PairingCode, User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("VAULT_KEY", "y" * 32)
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("MAGIC_LINK_BASE_URL", "https://app.example.com")


@pytest.fixture
async def db_session_factory():
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
            ],
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def client(db_session_factory, monkeypatch):
    import daily.auth.router as auth_router_module

    monkeypatch.setattr(auth_router_module, "async_session", db_session_factory)

    from daily.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, db_session_factory


# ---------------------------------------------------------------------------
# Test 1: Returns 204 No Content
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_link_returns_204(client, monkeypatch):
    """POST /auth/pair/send-link returns 204 No Content."""
    import daily.auth.router as router_mod

    async def fake_send(email, code, *, settings):
        pass

    monkeypatch.setattr(router_mod, "send_magic_link", fake_send)

    ac, _ = client
    r = await ac.post("/auth/pair/send-link", json={"email": "user@example.com"})
    assert r.status_code == 204


# ---------------------------------------------------------------------------
# Test 2: PairingCode row inserted with correct fields
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_link_inserts_pairing_code(client, monkeypatch):
    """A PairingCode row is inserted with correct code, expiry, and consumed state."""
    import daily.auth.router as router_mod

    async def fake_send(email, code, *, settings):
        pass

    monkeypatch.setattr(router_mod, "send_magic_link", fake_send)

    ac, db_factory = client
    await ac.post("/auth/pair/send-link", json={"email": "user2@example.com"})

    async with db_factory() as session:
        result = await session.execute(select(PairingCode))
        rows = list(result.scalars())
        assert len(rows) == 1
        pc = rows[0]
        assert len(pc.code) == 6 and pc.code.isdigit()
        assert pc.expires_at is not None
        assert not pc.used


# ---------------------------------------------------------------------------
# Test 3: send_magic_link called once with correct email and code
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_link_calls_send_magic_link(client, monkeypatch):
    """send_magic_link is called once with the submitted email and the generated code."""
    import daily.auth.router as router_mod

    calls = []

    async def fake_send(email, code, *, settings):
        calls.append({"email": email, "code": code})

    monkeypatch.setattr(router_mod, "send_magic_link", fake_send)

    ac, db_factory = client
    await ac.post("/auth/pair/send-link", json={"email": "user3@example.com"})

    assert len(calls) == 1
    assert calls[0]["email"] == "user3@example.com"
    assert len(calls[0]["code"]) == 6


# ---------------------------------------------------------------------------
# Test 4: Returns 204 even when Resend raises ResendError (no enumeration leak)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_link_returns_204_on_resend_error(client, monkeypatch):
    """Endpoint returns 204 even when send_magic_link raises ResendError."""
    import daily.auth.router as router_mod
    from daily.email.resend_client import ResendError

    async def fake_send_error(email, code, *, settings):
        raise ResendError("Resend API error")

    monkeypatch.setattr(router_mod, "send_magic_link", fake_send_error)

    ac, _ = client
    r = await ac.post("/auth/pair/send-link", json={"email": "user4@example.com"})
    assert r.status_code == 204


# ---------------------------------------------------------------------------
# Test 5: Invalid email returns 422
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_link_rejects_invalid_email(client, monkeypatch):
    """Invalid email (no @) returns 422 from Pydantic validation."""
    import daily.auth.router as router_mod

    async def fake_send(email, code, *, settings):
        pass

    monkeypatch.setattr(router_mod, "send_magic_link", fake_send)

    ac, _ = client
    r = await ac.post("/auth/pair/send-link", json={"email": "not-an-email"})
    assert r.status_code == 422
