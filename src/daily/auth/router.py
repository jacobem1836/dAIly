"""Auth endpoints: pairing + token refresh (Phase 18, D-01..D-04)."""
import base64
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from daily.auth.jwt import encode_access_token
from daily.auth.pairing import (
    PAIRING_CODE_TTL_SECONDS,
    code_expiry,
    generate_pairing_code,
    generate_refresh_token,
)
from daily.config import Settings
from daily.db.engine import async_session
from daily.db.models import DeviceToken, PairingCode, User
from daily.email.resend_client import ResendError, send_magic_link
from daily.vault.crypto import decrypt_token, encrypt_token

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


async def _get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


def _get_settings() -> Settings:
    return Settings()


class SendLinkRequest(BaseModel):
    email: EmailStr


class InitiateRequest(BaseModel):
    user_id: int


class InitiateResponse(BaseModel):
    code: str
    expires_in: int


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


@router.post("/pair/send-link", status_code=204)
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


@router.post("/pair/initiate", response_model=InitiateResponse)
async def pair_initiate(
    body: InitiateRequest,
    session: AsyncSession = Depends(_get_db),
) -> InitiateResponse:
    # Auto-create user if missing (per Open Question 1 recommendation in RESEARCH.md)
    user = await session.get(User, body.user_id)
    if user is None:
        user = User(id=body.user_id)
        session.add(user)
        await session.flush()

    code = generate_pairing_code()
    pc = PairingCode(user_id=user.id, code=code, expires_at=code_expiry())
    session.add(pc)
    await session.commit()
    return InitiateResponse(code=code, expires_in=PAIRING_CODE_TTL_SECONDS)


@router.post("/pair/complete", response_model=CompleteResponse)
async def pair_complete(
    body: CompleteRequest,
    session: AsyncSession = Depends(_get_db),
    settings: Settings = Depends(_get_settings),
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
    key = base64.b64decode(settings.vault_key) if isinstance(settings.vault_key, str) else settings.vault_key
    encrypted = encrypt_token(refresh, key)
    expires_at = now + timedelta(days=settings.jwt_refresh_ttl_days)
    dt = DeviceToken(
        user_id=user_id,
        device_name=body.device_name,
        encrypted_refresh_token=encrypted,
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


@router.post("/token/refresh", response_model=RefreshResponse)
async def token_refresh(
    body: RefreshRequest,
    session: AsyncSession = Depends(_get_db),
    settings: Settings = Depends(_get_settings),
) -> RefreshResponse:
    now = datetime.now(timezone.utc)
    # Scan unrevoked, unexpired tokens; decrypt and compare.
    # Acceptable for v1.4 scale; for higher scale, store a hash alongside ciphertext.
    stmt = select(DeviceToken).where(
        DeviceToken.revoked.is_(False),
        DeviceToken.expires_at > now,
    )
    result = await session.execute(stmt)
    key = base64.b64decode(settings.vault_key) if isinstance(settings.vault_key, str) else settings.vault_key
    for dt in result.scalars():
        try:
            if decrypt_token(dt.encrypted_refresh_token, key) == body.refresh_token:
                dt.last_used_at = now
                await session.commit()
                access = encode_access_token(dt.user_id, settings)
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
