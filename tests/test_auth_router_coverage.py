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


@pytest.fixture
async def fake_redis():
    """fakeredis instance for pair_complete's failed-attempt tracking.

    pair_complete now takes a ``redis`` parameter (security fix, wave 1 —
    failed pairing-code guess counter). Direct function calls in this file
    bypass FastAPI's dependency injection, so it must be passed explicitly.
    """
    import fakeredis.aioredis as fake_aioredis

    client = fake_aioredis.FakeRedis()
    yield client
    await client.aclose()


@pytest.fixture
def fake_request():
    """Minimal stand-in for FastAPI's Request — only .client.host is used."""
    request = MagicMock()
    request.client.host = "127.0.0.1"
    return request


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
async def test_pair_complete_invalid_code_raises_400(db_factory, settings, fake_redis, fake_request):
    """pair_complete with wrong code → HTTPException 400."""
    from fastapi import HTTPException
    from daily.auth.router import CompleteRequest, pair_complete

    async with db_factory() as session:
        req = CompleteRequest(code="000000")
        with pytest.raises(HTTPException) as exc:
            await pair_complete(fake_request, req, session=session, settings=settings, redis=fake_redis)
        assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_pair_complete_magic_link_new_user(db_factory, settings, fake_redis, fake_request):
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
        resp = await pair_complete(fake_request, req, session=session, settings=settings, redis=fake_redis)
        assert resp.access_token
        assert resp.refresh_token


@pytest.mark.asyncio
async def test_pair_complete_magic_link_existing_user(db_factory, settings, fake_redis, fake_request):
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
        resp = await pair_complete(fake_request, req, session=session, settings=settings, redis=fake_redis)
        assert resp.access_token


@pytest.mark.asyncio
async def test_pair_complete_expired_code_raises_400(db_factory, settings, fake_redis, fake_request):
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
            await pair_complete(fake_request, req, session=session, settings=settings, redis=fake_redis)
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# token_refresh — success + 401 paths (lines 202-215)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_refresh_success(db_factory, settings, fake_redis, fake_request):
    """token_refresh finds matching token and returns new access token."""
    from daily.auth.router import CompleteRequest, RefreshRequest, pair_complete, token_refresh

    code = await _seed_pairing_code(db_factory, user_id=55)

    async with db_factory() as session:
        complete_resp = await pair_complete(
            fake_request, CompleteRequest(code=code), session=session, settings=settings, redis=fake_redis
        )

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
async def test_token_refresh_revoked_token_raises_401(db_factory, settings, fake_redis, fake_request):
    """token_refresh with revoked DeviceToken → HTTPException 401."""
    from fastapi import HTTPException
    from sqlalchemy import update
    from daily.auth.router import CompleteRequest, RefreshRequest, pair_complete, token_refresh

    code = await _seed_pairing_code(db_factory, user_id=66)

    async with db_factory() as session:
        complete_resp = await pair_complete(
            fake_request, CompleteRequest(code=code), session=session, settings=settings, redis=fake_redis
        )

    async with db_factory() as session:
        await session.execute(update(DeviceToken).where(DeviceToken.user_id == 66).values(revoked=True))
        await session.commit()

    async with db_factory() as session:
        with pytest.raises(HTTPException) as exc:
            await token_refresh(RefreshRequest(refresh_token=complete_resp.refresh_token), session=session, settings=settings)
        assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# refresh_token_hash indexed lookup + legacy NULL-hash fallback (audit C4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pair_complete_populates_refresh_token_hash(db_factory, settings, fake_redis, fake_request):
    """pair_complete stores a SHA-256 hash of the raw refresh token alongside the ciphertext."""
    import hashlib
    from sqlalchemy import select
    from daily.auth.router import CompleteRequest, pair_complete

    code = await _seed_pairing_code(db_factory, user_id=77)

    async with db_factory() as session:
        complete_resp = await pair_complete(
            fake_request, CompleteRequest(code=code), session=session, settings=settings, redis=fake_redis
        )

    expected_hash = hashlib.sha256(complete_resp.refresh_token.encode()).hexdigest()
    async with db_factory() as session:
        row = (
            await session.execute(select(DeviceToken).where(DeviceToken.user_id == 77))
        ).scalar_one()
    assert row.refresh_token_hash == expected_hash


@pytest.mark.asyncio
async def test_token_refresh_uses_indexed_hash_fast_path(db_factory, settings, fake_redis, fake_request):
    """token_refresh finds the row via refresh_token_hash without needing to decrypt any other row."""
    from daily.auth.router import CompleteRequest, RefreshRequest, pair_complete, token_refresh

    # Seed several decoy devices plus the target device — if the fast path
    # regressed to a full scan, this would still pass; the point is that the
    # hash-matched row is the one and only one returned by the indexed query.
    for uid in (81, 82, 83):
        code = await _seed_pairing_code(db_factory, user_id=uid)
        async with db_factory() as session:
            await pair_complete(
                fake_request, CompleteRequest(code=code), session=session, settings=settings, redis=fake_redis
            )

    code = await _seed_pairing_code(db_factory, user_id=84)
    async with db_factory() as session:
        complete_resp = await pair_complete(
            fake_request, CompleteRequest(code=code), session=session, settings=settings, redis=fake_redis
        )

    async with db_factory() as session:
        resp = await token_refresh(
            RefreshRequest(refresh_token=complete_resp.refresh_token), session=session, settings=settings
        )
    assert resp.access_token


@pytest.mark.asyncio
async def test_token_refresh_falls_back_to_legacy_null_hash_row(db_factory, settings):
    """A pre-migration DeviceToken row (refresh_token_hash=NULL) is still refreshable.

    Simulates a device paired before the refresh_token_hash column existed.
    token_refresh must fall back to decrypting NULL-hash rows to find a
    match, then backfill the hash so the next refresh hits the fast path.
    """
    import hashlib
    from sqlalchemy import select
    from daily.auth.router import RefreshRequest, token_refresh
    from daily.vault.crypto import encrypt_token, load_vault_key

    raw_refresh = "legacy-raw-refresh-token-value"
    key = load_vault_key(settings.vault_key)

    async with db_factory() as session:
        session.add(User(id=91))
        session.add(
            DeviceToken(
                user_id=91,
                encrypted_refresh_token=encrypt_token(raw_refresh, key),
                refresh_token_hash=None,  # pre-migration row
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                revoked=False,
            )
        )
        await session.commit()

    async with db_factory() as session:
        resp = await token_refresh(RefreshRequest(refresh_token=raw_refresh), session=session, settings=settings)
    assert resp.access_token

    expected_hash = hashlib.sha256(raw_refresh.encode()).hexdigest()
    async with db_factory() as session:
        row = (
            await session.execute(select(DeviceToken).where(DeviceToken.user_id == 91))
        ).scalar_one()
    assert row.refresh_token_hash == expected_hash


@pytest.mark.asyncio
async def test_token_refresh_legacy_null_hash_row_wrong_token_raises_401(db_factory, settings):
    """A NULL-hash row that doesn't match the presented token still results in 401."""
    from fastapi import HTTPException
    from daily.auth.router import RefreshRequest, token_refresh
    from daily.vault.crypto import encrypt_token, load_vault_key

    key = load_vault_key(settings.vault_key)

    async with db_factory() as session:
        session.add(User(id=92))
        session.add(
            DeviceToken(
                user_id=92,
                encrypted_refresh_token=encrypt_token("some-other-token", key),
                refresh_token_hash=None,
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                revoked=False,
            )
        )
        await session.commit()

    async with db_factory() as session:
        with pytest.raises(HTTPException) as exc:
            await token_refresh(RefreshRequest(refresh_token="wrong-token"), session=session, settings=settings)
        assert exc.value.status_code == 401
