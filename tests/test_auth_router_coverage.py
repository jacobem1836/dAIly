"""Coverage uplift for auth/router.py — calls endpoint functions directly.

Tests branches NOT covered by test_auth_pairing.py / test_auth_send_link.py:
- pair_send_link try/except block (lines 91-99)
- pair_complete magic-link flow (user_id=None paths)
- token_refresh success + revoked paths

Direct function calls bypass ASGI transport so coverage.py traces async bodies.
"""
import base64
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from daily.db.models import Base, DeviceToken, PairingCode, User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("VAULT_KEY", base64.b64encode(b"y" * 32).decode())
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("MAGIC_LINK_BASE_URL", "https://app.example.com")


@pytest.fixture
async def db_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[User.__table__, PairingCode.__table__, DeviceToken.__table__],
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def settings():
    from daily.config import Settings
    return Settings()


async def _seed_pairing_code(db_factory, user_id: int) -> str:
    """Create a User + an unused, unexpired PairingCode row for that user.

    Replaces the deleted pair_initiate endpoint for test setup (security
    fix, wave 1 audit remediation — pair_initiate allowed unauthenticated
    account takeover and was unused by the iOS app).
    """
    from daily.auth.pairing import code_expiry, generate_pairing_code

    code = generate_pairing_code()
    async with db_factory() as session:
        session.add(User(id=user_id))
        session.add(PairingCode(user_id=user_id, code=code, expires_at=code_expiry()))
        await session.commit()
    return code


# ---------------------------------------------------------------------------
# pair_send_link — try/except block (lines 91-99)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_link_success_path_try_block(db_factory, settings):
    """pair_send_link try block executes when send_magic_link succeeds."""
    from daily.auth.router import SendLinkRequest, pair_send_link

    async with db_factory() as session:
        req = SendLinkRequest(email="test@example.com")
        with patch("daily.auth.router.send_magic_link", new_callable=AsyncMock) as mock_send:
            result = await pair_send_link(req, session=session, settings=settings)
        mock_send.assert_called_once()
        assert result is None


@pytest.mark.asyncio
async def test_send_link_resend_error_swallowed(db_factory, settings):
    """pair_send_link swallows ResendError and returns None (no enumeration)."""
    from daily.auth.router import SendLinkRequest, pair_send_link
    from daily.email.resend_client import ResendError

    async with db_factory() as session:
        req = SendLinkRequest(email="err@example.com")
        with patch("daily.auth.router.send_magic_link", new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = ResendError("Resend down")
            result = await pair_send_link(req, session=session, settings=settings)
        assert result is None


# ---------------------------------------------------------------------------
# pair_complete — magic-link flow (lines 140-181)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pair_complete_invalid_code_raises_400(db_factory, settings):
    """pair_complete with wrong code → HTTPException 400."""
    from fastapi import HTTPException
    from daily.auth.router import CompleteRequest, pair_complete

    async with db_factory() as session:
        req = CompleteRequest(code="000000")
        with pytest.raises(HTTPException) as exc:
            await pair_complete(req, session=session, settings=settings)
        assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_pair_complete_magic_link_new_user(db_factory, settings):
    """pair_complete magic-link flow creates new User when none exists for email."""
    from daily.auth.pairing import generate_pairing_code, code_expiry
    from daily.auth.router import CompleteRequest, pair_complete

    code = generate_pairing_code()
    async with db_factory() as session:
        pc = PairingCode(code=code, expires_at=code_expiry(), email="new@example.com", user_id=None)
        session.add(pc)
        await session.commit()

    async with db_factory() as session:
        req = CompleteRequest(code=code)
        resp = await pair_complete(req, session=session, settings=settings)
        assert resp.access_token
        assert resp.refresh_token


@pytest.mark.asyncio
async def test_pair_complete_magic_link_existing_user(db_factory, settings):
    """pair_complete magic-link flow reuses existing user found via prior pairing codes."""
    from daily.auth.pairing import generate_pairing_code, code_expiry
    from daily.auth.router import CompleteRequest, pair_complete

    async with db_factory() as session:
        user = User(id=77)
        session.add(user)
        old_code = PairingCode(code=generate_pairing_code(), expires_at=code_expiry(), email="existing@example.com", user_id=77, used=True)
        session.add(old_code)
        await session.commit()

    code = generate_pairing_code()
    async with db_factory() as session:
        pc = PairingCode(code=code, expires_at=code_expiry(), email="existing@example.com", user_id=None)
        session.add(pc)
        await session.commit()

    async with db_factory() as session:
        req = CompleteRequest(code=code)
        resp = await pair_complete(req, session=session, settings=settings)
        assert resp.access_token


@pytest.mark.asyncio
async def test_pair_complete_expired_code_raises_400(db_factory, settings):
    """pair_complete with expired pairing code → HTTPException 400."""
    from fastapi import HTTPException
    from daily.auth.pairing import generate_pairing_code
    from daily.auth.router import CompleteRequest, pair_complete

    code = generate_pairing_code()
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    async with db_factory() as session:
        pc = PairingCode(code=code, expires_at=past, email="x@example.com", user_id=None)
        session.add(pc)
        await session.commit()

    async with db_factory() as session:
        req = CompleteRequest(code=code)
        with pytest.raises(HTTPException) as exc:
            await pair_complete(req, session=session, settings=settings)
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# token_refresh — success + 401 paths (lines 202-215)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_refresh_success(db_factory, settings):
    """token_refresh finds matching token and returns new access token."""
    from daily.auth.router import CompleteRequest, RefreshRequest, pair_complete, token_refresh

    code = await _seed_pairing_code(db_factory, user_id=55)

    async with db_factory() as session:
        complete_resp = await pair_complete(CompleteRequest(code=code), session=session, settings=settings)

    async with db_factory() as session:
        resp = await token_refresh(RefreshRequest(refresh_token=complete_resp.refresh_token), session=session, settings=settings)
        assert resp.access_token
        assert resp.expires_in > 0


@pytest.mark.asyncio
async def test_token_refresh_invalid_token_raises_401(db_factory, settings):
    """token_refresh with garbage token → HTTPException 401."""
    from fastapi import HTTPException
    from daily.auth.router import RefreshRequest, token_refresh

    async with db_factory() as session:
        with pytest.raises(HTTPException) as exc:
            await token_refresh(RefreshRequest(refresh_token="garbage-token"), session=session, settings=settings)
        assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_token_refresh_revoked_token_raises_401(db_factory, settings):
    """token_refresh with revoked DeviceToken → HTTPException 401."""
    from fastapi import HTTPException
    from sqlalchemy import update
    from daily.auth.router import CompleteRequest, RefreshRequest, pair_complete, token_refresh

    code = await _seed_pairing_code(db_factory, user_id=66)

    async with db_factory() as session:
        complete_resp = await pair_complete(CompleteRequest(code=code), session=session, settings=settings)

    async with db_factory() as session:
        await session.execute(update(DeviceToken).where(DeviceToken.user_id == 66).values(revoked=True))
        await session.commit()

    async with db_factory() as session:
        with pytest.raises(HTTPException) as exc:
            await token_refresh(RefreshRequest(refresh_token=complete_resp.refresh_token), session=session, settings=settings)
        assert exc.value.status_code == 401
