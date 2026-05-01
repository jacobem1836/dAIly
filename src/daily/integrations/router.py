"""Mobile-mediated OAuth router for Google, Microsoft (outlook), and Slack.

Each provider exposes two endpoints:
  - GET /integrations/{provider}/connect  — authenticated, returns auth_url
  - GET /integrations/{provider}/callback — validates CSRF state, exchanges code,
    encrypts and persists IntegrationToken, redirects to Universal Link

Security:
  T-21-03-01: CSRF — state token is secrets.token_urlsafe(32), stored in Redis with 600s
               TTL and deleted on first read (_consume_oauth_state) — single-use.
  T-21-03-02: All connect endpoints require Bearer JWT via get_current_user.
  T-21-03-04: Tokens immediately encrypted (AES-256-GCM) before DB write; never logged.
  T-21-03-07: Redirect target built from settings.magic_link_base_url (env-controlled).
  T-21-03-08: Microsoft stored as provider="outlook" to match existing CLI convention.
"""
import base64
import secrets
from datetime import datetime, timedelta, timezone as _tz
from urllib.parse import urlencode

import httpx
import msal
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from daily.auth.deps import get_current_user
from daily.config import Settings
from daily.db.engine import async_session
from daily.db.models import IntegrationToken, User
from daily.integrations.google.auth import GOOGLE_ACTION_SCOPES
from daily.integrations.microsoft.auth import MICROSOFT_READONLY_SCOPES
from daily.integrations.slack.auth import SLACK_AUTHORIZE_URL, SLACK_BOT_SCOPES, SLACK_TOKEN_URL
from daily.vault.crypto import encrypt_token

router = APIRouter(prefix="/integrations", tags=["integrations"])

OAUTH_STATE_TTL_SECONDS = 600


# ---------------------------------------------------------------------------
# Shared dependency helpers
# ---------------------------------------------------------------------------


async def _get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


def _get_settings() -> Settings:
    return Settings()


async def _get_redis():
    settings = Settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        yield redis
    finally:
        await redis.aclose()


def _vault_key(settings: Settings) -> bytes:
    """Decode the vault key from settings (base64 string or raw bytes)."""
    raw = settings.vault_key
    if isinstance(raw, bytes):
        return raw
    # Handle both base64-encoded and raw 32-char strings
    try:
        decoded = base64.b64decode(raw)
        if len(decoded) == 32:
            return decoded
    except Exception:
        pass
    # Fall back to UTF-8 bytes (e.g. test fixtures using "y" * 32)
    return raw.encode()


async def _consume_oauth_state(redis: Redis, state: str) -> int:
    """Validate and consume an OAuth CSRF state token from Redis.

    T-21-03-01: Single-use — deleted on first read.

    Args:
        redis: Async Redis client.
        state: The state token from the OAuth callback query parameter.

    Returns:
        user_id stored when the state was created.

    Raises:
        HTTPException 400: If state is not found or already consumed.
    """
    raw = await redis.get(f"oauth_state:{state}")
    if raw is None:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
    await redis.delete(f"oauth_state:{state}")
    return int(raw.decode() if isinstance(raw, bytes) else raw)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ConnectResponse(BaseModel):
    auth_url: str


# ---------------------------------------------------------------------------
# Google
# ---------------------------------------------------------------------------


def _google_client_config(settings: Settings, redirect_uri: str) -> dict:
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uris": [redirect_uri],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


@router.get("/google/connect", response_model=ConnectResponse)
async def google_connect(
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(_get_settings),
    redis: Redis = Depends(_get_redis),
) -> ConnectResponse:
    """Return a Google OAuth authorization URL. Stores CSRF state in Redis.

    T-21-03-02: Requires valid Bearer JWT.
    T-21-03-01: Generates a random state token stored in Redis with 600s TTL.
    """
    state = secrets.token_urlsafe(32)
    await redis.setex(f"oauth_state:{state}", OAUTH_STATE_TTL_SECONDS, str(current_user.id))

    redirect_uri = f"{settings.magic_link_base_url}/integrations/google/callback"
    flow = Flow.from_client_config(
        _google_client_config(settings, redirect_uri),
        scopes=GOOGLE_ACTION_SCOPES,
        redirect_uri=redirect_uri,
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
        include_granted_scopes="true",
    )
    return ConnectResponse(auth_url=auth_url)


@router.get("/google/callback")
async def google_callback(
    code: str,
    state: str,
    session: AsyncSession = Depends(_get_db),
    settings: Settings = Depends(_get_settings),
    redis: Redis = Depends(_get_redis),
) -> RedirectResponse:
    """Exchange Google authorization code for tokens; encrypt and persist.

    T-21-03-01: Validates and deletes state from Redis (single-use).
    T-21-03-04: Tokens encrypted before DB write; never logged.
    T-21-03-07: Redirects to settings.magic_link_base_url/oauth/success?provider=google.
    """
    user_id = await _consume_oauth_state(redis, state)

    redirect_uri = f"{settings.magic_link_base_url}/integrations/google/callback"
    flow = Flow.from_client_config(
        _google_client_config(settings, redirect_uri),
        scopes=GOOGLE_ACTION_SCOPES,
        redirect_uri=redirect_uri,
    )
    flow.fetch_token(code=code)
    creds = flow.credentials

    key = _vault_key(settings)
    encrypted_access = encrypt_token(creds.token, key)
    encrypted_refresh = encrypt_token(creds.refresh_token, key) if creds.refresh_token else None
    scopes_str = " ".join(creds.scopes) if creds.scopes else " ".join(GOOGLE_ACTION_SCOPES)

    await session.execute(
        delete(IntegrationToken).where(
            IntegrationToken.user_id == user_id,
            IntegrationToken.provider == "google",
        )
    )
    session.add(
        IntegrationToken(
            user_id=user_id,
            provider="google",
            encrypted_access_token=encrypted_access,
            encrypted_refresh_token=encrypted_refresh,
            token_expiry=creds.expiry,
            scopes=scopes_str,
        )
    )
    await session.commit()

    return RedirectResponse(
        url=f"{settings.magic_link_base_url}/oauth/success?provider=google",
        status_code=302,
    )


# ---------------------------------------------------------------------------
# Microsoft (provider="outlook" — matches existing CLI convention)
# ---------------------------------------------------------------------------


def _msal_app(settings: Settings) -> msal.ConfidentialClientApplication:
    """Build an MSAL ConfidentialClientApplication from settings."""
    authority = f"https://login.microsoftonline.com/{settings.microsoft_tenant_id}"
    return msal.ConfidentialClientApplication(
        settings.microsoft_client_id,
        client_credential=settings.microsoft_client_secret,
        authority=authority,
    )


@router.get("/microsoft/connect", response_model=ConnectResponse)
async def microsoft_connect(
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(_get_settings),
    redis: Redis = Depends(_get_redis),
) -> ConnectResponse:
    """Return a Microsoft OAuth authorization URL. Stores CSRF state in Redis.

    T-21-03-02: Requires valid Bearer JWT.
    """
    state = secrets.token_urlsafe(32)
    await redis.setex(f"oauth_state:{state}", OAUTH_STATE_TTL_SECONDS, str(current_user.id))

    redirect_uri = f"{settings.magic_link_base_url}/integrations/microsoft/callback"
    msal_app = _msal_app(settings)
    auth_url = msal_app.get_authorization_request_url(
        MICROSOFT_READONLY_SCOPES,
        state=state,
        redirect_uri=redirect_uri,
    )
    return ConnectResponse(auth_url=auth_url)


@router.get("/microsoft/callback")
async def microsoft_callback(
    code: str,
    state: str,
    session: AsyncSession = Depends(_get_db),
    settings: Settings = Depends(_get_settings),
    redis: Redis = Depends(_get_redis),
) -> RedirectResponse:
    """Exchange Microsoft authorization code for tokens; encrypt and persist.

    T-21-03-08: Stores with provider="outlook" (NOT "microsoft") to match CLI convention.
    T-21-03-04: Tokens encrypted before DB write.
    """
    user_id = await _consume_oauth_state(redis, state)

    redirect_uri = f"{settings.magic_link_base_url}/integrations/microsoft/callback"
    msal_app = _msal_app(settings)
    result = msal_app.acquire_token_by_authorization_code(
        code,
        scopes=MICROSOFT_READONLY_SCOPES,
        redirect_uri=redirect_uri,
    )
    if "access_token" not in result:
        raise HTTPException(
            status_code=400,
            detail=f"Microsoft token exchange failed: {result.get('error_description', 'unknown')}",
        )

    key = _vault_key(settings)
    encrypted_access = encrypt_token(result["access_token"], key)
    encrypted_refresh = (
        encrypt_token(result["refresh_token"], key) if result.get("refresh_token") else None
    )
    expiry = None
    if "expires_in" in result:
        expiry = datetime.now(_tz.utc) + timedelta(seconds=int(result["expires_in"]))
    scopes_str = " ".join(MICROSOFT_READONLY_SCOPES)

    await session.execute(
        delete(IntegrationToken).where(
            IntegrationToken.user_id == user_id,
            IntegrationToken.provider == "outlook",
        )
    )
    session.add(
        IntegrationToken(
            user_id=user_id,
            provider="outlook",  # CONVENTION: matches existing CLI flow (NOT "microsoft")
            encrypted_access_token=encrypted_access,
            encrypted_refresh_token=encrypted_refresh,
            token_expiry=expiry,
            scopes=scopes_str,
        )
    )
    await session.commit()

    return RedirectResponse(
        url=f"{settings.magic_link_base_url}/oauth/success?provider=microsoft",
        status_code=302,
    )


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------


@router.get("/slack/connect", response_model=ConnectResponse)
async def slack_connect(
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(_get_settings),
    redis: Redis = Depends(_get_redis),
) -> ConnectResponse:
    """Return a Slack OAuth V2 authorization URL. Stores CSRF state in Redis.

    T-21-03-02: Requires valid Bearer JWT.
    """
    state = secrets.token_urlsafe(32)
    await redis.setex(f"oauth_state:{state}", OAUTH_STATE_TTL_SECONDS, str(current_user.id))

    redirect_uri = f"{settings.magic_link_base_url}/integrations/slack/callback"
    params = {
        "client_id": settings.slack_client_id,
        "scope": ",".join(SLACK_BOT_SCOPES),
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return ConnectResponse(auth_url=f"{SLACK_AUTHORIZE_URL}?{urlencode(params)}")


@router.get("/slack/callback")
async def slack_callback(
    code: str,
    state: str,
    session: AsyncSession = Depends(_get_db),
    settings: Settings = Depends(_get_settings),
    redis: Redis = Depends(_get_redis),
) -> RedirectResponse:
    """Exchange Slack authorization code for bot token; encrypt and persist.

    Uses async httpx to POST to oauth.v2.access.
    T-21-03-04: Bot token encrypted before DB write.
    """
    user_id = await _consume_oauth_state(redis, state)

    redirect_uri = f"{settings.magic_link_base_url}/integrations/slack/callback"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            SLACK_TOKEN_URL,
            data={
                "client_id": settings.slack_client_id,
                "client_secret": settings.slack_client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )
    resp.raise_for_status()
    data = resp.json()

    if not data.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=f"Slack OAuth error: {data.get('error', 'unknown')}",
        )

    bot_token = data["access_token"]
    key = _vault_key(settings)
    encrypted_access = encrypt_token(bot_token, key)
    scopes_str = " ".join(SLACK_BOT_SCOPES)

    await session.execute(
        delete(IntegrationToken).where(
            IntegrationToken.user_id == user_id,
            IntegrationToken.provider == "slack",
        )
    )
    session.add(
        IntegrationToken(
            user_id=user_id,
            provider="slack",
            encrypted_access_token=encrypted_access,
            encrypted_refresh_token=None,
            token_expiry=None,
            scopes=scopes_str,
        )
    )
    await session.commit()

    return RedirectResponse(
        url=f"{settings.magic_link_base_url}/oauth/success?provider=slack",
        status_code=302,
    )
