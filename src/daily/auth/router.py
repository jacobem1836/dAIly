"""Auth endpoints: pairing + token refresh (Phase 18, D-01..D-04)."""
import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from daily.auth.jwt import encode_access_token
from daily.auth.pairing import (
    PAIRING_CODE_TTL_SECONDS,
    code_expiry,
    generate_pairing_code,
    generate_refresh_token,
)
from daily.auth.ratelimit import RateLimiter, client_ip, get_redis
from daily.config import Settings
from daily.db.engine import async_session
from daily.db.models import DeviceToken, PairingCode, User
from daily.email.resend_client import ResendError, send_magic_link
from daily.vault.crypto import decrypt_token, encrypt_token, load_vault_key

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Security fix (wave 1 audit remediation, CRITICAL): a 6-digit pairing code
# has a 900k-value search space and a 5-minute TTL — brute-forceable without
# rate limiting. These limits are deliberately generous for legitimate users
# (typos, retries) while making brute force impractical.
_SEND_LINK_RATE_LIMIT = RateLimiter("pair_send_link", limit=10, window_seconds=60)
_PAIR_COMPLETE_RATE_LIMIT = RateLimiter("pair_complete", limit=20, window_seconds=300)
_TOKEN_REFRESH_RATE_LIMIT = RateLimiter("token_refresh", limit=20, window_seconds=300)

# After this many failed pairing-code guesses from the same client within
# one pairing-code lifetime, proactively invalidate all currently pending
# (unused, unexpired) pairing codes — forces re-issuance rather than letting
# an attacker keep guessing against a live window.
_MAX_FAILED_PAIR_ATTEMPTS = 5


def _hash_refresh_token(raw_token: str) -> str:
    """SHA-256 hex digest of a raw refresh token (audit C4).

    Stored alongside the encrypted ciphertext so /auth/token/refresh can do
    an indexed equality lookup instead of decrypting every device token in
    the table. Not a secret itself (one-way, and the raw token is required
    to derive it) so plain SHA-256 is sufficient here — this is a lookup
    key, not a password hash.
    """
    return hashlib.sha256(raw_token.encode()).hexdigest()


async def _get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


def _get_settings() -> Settings:
    return Settings()


class SendLinkRequest(BaseModel):
    email: EmailStr


class CompleteRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    device_name: str | None = None


class CompleteResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    expires_in: int


@router.post(
    "/pair/send-link",
    status_code=204,
    dependencies=[Depends(_SEND_LINK_RATE_LIMIT)],
)
async def pair_send_link(
    req: SendLinkRequest,
    session: AsyncSession = Depends(_get_db),
    settings: Settings = Depends(_get_settings),
) -> None:
    """Generate a pairing code and send a magic-link email via Resend.

    Always returns 204 — never confirms whether the email is registered or
    whether Resend delivery succeeded (prevents email enumeration, T-19-01).
    """
    code = generate_pairing_code()
    pc = PairingCode(
        code=code,
        expires_at=code_expiry(),
        email=str(req.email),
        user_id=None,
    )
    session.add(pc)
    await session.commit()
    try:
        await send_magic_link(str(req.email), code, settings=settings)
    except ResendError as exc:
        _logger.error(
            "magic_link_send_failed email_hash=%s error=%s",
            hash(str(req.email)),
            str(exc),
        )
    return None


async def _register_failed_pair_attempt(redis: Redis, request: Request, session: AsyncSession) -> None:
    """Track failed pairing-code guesses per client IP.

    Security fix (wave 1 audit remediation): beyond generic rate limiting,
    once a client racks up too many wrong guesses within one pairing-code
    lifetime, we proactively invalidate every currently pending (unused,
    unexpired) PairingCode row. The request has no way to identify which
    code was actually being targeted, so this trades some legitimate-user
    friction (forced re-issuance) for closing the window an attacker is
    brute-forcing against.
    """
    key = f"pairfail:{client_ip(request)}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, PAIRING_CODE_TTL_SECONDS)
    if count >= _MAX_FAILED_PAIR_ATTEMPTS:
        now = datetime.now(timezone.utc)
        await session.execute(
            update(PairingCode)
            .where(PairingCode.used.is_(False), PairingCode.expires_at > now)
            .values(used=True)
        )
        await session.commit()
        await redis.delete(key)


@router.post(
    "/pair/complete",
    response_model=CompleteResponse,
    dependencies=[Depends(_PAIR_COMPLETE_RATE_LIMIT)],
)
async def pair_complete(
    request: Request,
    body: CompleteRequest,
    session: AsyncSession = Depends(_get_db),
    settings: Settings = Depends(_get_settings),
    redis: Redis = Depends(get_redis),
) -> CompleteResponse:
    # Atomic compare-and-swap to prevent race (RESEARCH.md Pitfall 4)
    now = datetime.now(timezone.utc)
    stmt = (
        update(PairingCode)
        .where(
            PairingCode.code == body.code,
            PairingCode.used.is_(False),
            PairingCode.expires_at > now,
        )
        .values(used=True)
        .returning(PairingCode.id, PairingCode.user_id, PairingCode.email)
    )
    result = await session.execute(stmt)
    row = result.first()
    if row is None:
        await session.rollback()
        await _register_failed_pair_attempt(redis, request, session)
        raise HTTPException(status_code=400, detail="Invalid, used, or expired pairing code")
    _, user_id, pairing_email = row

    # Magic-link flow: user_id is null — find existing user by email in pairing codes
    # or create a new user row (User table has no email column; email lives on PairingCode)
    if user_id is None:
        if not pairing_email:
            await session.rollback()
            raise HTTPException(status_code=400, detail="Pairing code has no associated email")
        # Check if a user already exists with a prior pairing code for this email
        prior = await session.execute(
            select(PairingCode.user_id)
            .where(PairingCode.email == pairing_email, PairingCode.user_id.is_not(None))
            .limit(1)
        )
        existing_user_id = prior.scalar_one_or_none()
        if existing_user_id is not None:
            user_id = existing_user_id
        else:
            user = User()
            session.add(user)
            await session.flush()
            user_id = user.id

    refresh = generate_refresh_token()
    key = load_vault_key(settings.vault_key)
    encrypted = encrypt_token(refresh, key)
    expires_at = now + timedelta(days=settings.jwt_refresh_ttl_days)
    dt = DeviceToken(
        user_id=user_id,
        device_name=body.device_name,
        encrypted_refresh_token=encrypted,
        refresh_token_hash=_hash_refresh_token(refresh),
        expires_at=expires_at,
    )
    session.add(dt)
    await session.commit()

    access = encode_access_token(user_id, settings)
    return CompleteResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.jwt_access_ttl_minutes * 60,
    )


@router.post(
    "/token/refresh",
    response_model=RefreshResponse,
    dependencies=[Depends(_TOKEN_REFRESH_RATE_LIMIT)],
)
async def token_refresh(
    body: RefreshRequest,
    session: AsyncSession = Depends(_get_db),
    settings: Settings = Depends(_get_settings),
) -> RefreshResponse:
    """Exchange a refresh token for a new access token.

    Audit C4 fix: previously this scanned every unrevoked, unexpired
    DeviceToken row and AES-decrypted each one in a Python loop to find a
    match — O(all devices) per call. Now does an indexed lookup by
    refresh_token_hash (SHA-256 of the raw token) first, decrypting only
    the single matched row to confirm via constant-time compare.

    Legacy rows created before refresh_token_hash existed have it as NULL
    (the hash can't be derived from ciphertext without decrypting first).
    Those fall back to the old per-row scan, but ONLY among NULL-hash rows
    — and a successful match backfills the hash so the device hits the
    fast indexed path on every subsequent refresh.
    """
    now = datetime.now(timezone.utc)
    key = load_vault_key(settings.vault_key)
    target_hash = _hash_refresh_token(body.refresh_token)

    # Fast path: indexed lookup by refresh_token_hash.
    stmt = select(DeviceToken).where(
        DeviceToken.refresh_token_hash == target_hash,
        DeviceToken.revoked.is_(False),
        DeviceToken.expires_at > now,
    )
    result = await session.execute(stmt)
    dt = result.scalar_one_or_none()
    if dt is not None:
        try:
            if hmac.compare_digest(decrypt_token(dt.encrypted_refresh_token, key), body.refresh_token):
                dt.last_used_at = now
                await session.commit()
                access = encode_access_token(dt.user_id, settings)
                return RefreshResponse(
                    access_token=access,
                    expires_in=settings.jwt_access_ttl_minutes * 60,
                )
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked refresh token",
        )

    # Fallback: legacy rows with no hash yet (nullable, backfilled lazily).
    # Scans only NULL-hash rows, never the whole table.
    legacy_stmt = select(DeviceToken).where(
        DeviceToken.refresh_token_hash.is_(None),
        DeviceToken.revoked.is_(False),
        DeviceToken.expires_at > now,
    )
    legacy_result = await session.execute(legacy_stmt)
    for legacy_dt in legacy_result.scalars():
        try:
            if hmac.compare_digest(decrypt_token(legacy_dt.encrypted_refresh_token, key), body.refresh_token):
                legacy_dt.last_used_at = now
                legacy_dt.refresh_token_hash = target_hash
                await session.commit()
                access = encode_access_token(legacy_dt.user_id, settings)
                return RefreshResponse(
                    access_token=access,
                    expires_in=settings.jwt_access_ttl_minutes * 60,
                )
        except Exception:
            continue

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or revoked refresh token",
    )
