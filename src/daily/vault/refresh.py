"""
Cross-provider OAuth token refresh logic.

Designed to be called by APScheduler in Phase 2, but the logic lives here
in the vault module so it is independently testable.

T-1-19: Refresh tokens are decrypted in-memory only; re-encrypted immediately
        after a successful refresh. Decrypted tokens are never logged.
T-1-21: Per-token error handling — one failed refresh does not block others.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from daily.db.models import IntegrationToken
from daily.vault.crypto import decrypt_token, encrypt_token

logger = logging.getLogger(__name__)


async def refresh_expiring_tokens(
    session_factory: Any,
    vault_key: bytes,
    buffer_minutes: int = 15,
) -> list[dict]:
    """Find tokens expiring within buffer_minutes and refresh them proactively.

    Queries for all IntegrationToken rows where token_expiry is not null and
    falls within the next buffer_minutes. For each expiring token, dispatches
    to the appropriate provider-specific refresh helper, re-encrypts the new
    access token, and updates the DB row.

    T-1-19: Refresh tokens are decrypted in-memory only — never logged, never
            passed to the LLM layer, re-encrypted immediately after refresh.
    T-1-21: Per-token exception handling — a single failed refresh is logged
            and included in results with success=False; processing continues.

    Args:
        session_factory: Async session factory from make_session_factory.
        vault_key: 32-byte AES-256 key from Settings.vault_key.
        buffer_minutes: Refresh tokens expiring within this many minutes (default 15).

    Returns:
        List of refresh result dicts:
        [{"provider": str, "user_id": int, "success": bool, "error": str | None}]
    """
    now = datetime.now(tz=timezone.utc)
    cutoff = now + timedelta(minutes=buffer_minutes)

    results: list[dict] = []

    async with session_factory() as session:
        # Fetch tokens expiring within the buffer window
        # Tokens with no expiry (e.g. Slack bot tokens) are excluded by IS NOT NULL
        stmt = select(IntegrationToken).where(
            IntegrationToken.token_expiry.isnot(None),
            IntegrationToken.token_expiry <= cutoff,
        )
        query_result = await session.execute(stmt)
        expiring_tokens = query_result.scalars().all()

        for token in expiring_tokens:
            result: dict = {
                "provider": token.provider,
                "user_id": token.user_id,
                "success": False,
                "error": None,
            }

            try:
                # T-1-19: Decrypt in-memory only
                if not token.encrypted_refresh_token:
                    raise ValueError(
                        f"No refresh token stored for provider={token.provider} user_id={token.user_id}"
                    )

                refresh_token_plain = decrypt_token(
                    token.encrypted_refresh_token, vault_key
                )

                # Dispatch to provider-specific refresh
                if token.provider == "google":
                    refresh_result = _refresh_google_token(refresh_token_plain)
                elif token.provider == "outlook":
                    scopes = token.scopes.split() if token.scopes else []
                    refresh_result = _refresh_microsoft_token(
                        refresh_token_plain, scopes=scopes
                    )
                else:
                    # Unknown provider — skip gracefully
                    logger.debug(
                        "Skipping unknown provider for token refresh: %s", token.provider
                    )
                    result["error"] = f"Unsupported provider: {token.provider}"
                    results.append(result)
                    continue

                # T-1-19: Re-encrypt new access token immediately
                new_access = refresh_result["access_token"]
                token.encrypted_access_token = encrypt_token(new_access, vault_key)

                # Re-encrypt new refresh token if provider rotated it
                new_refresh = refresh_result.get("refresh_token")
                if new_refresh:
                    token.encrypted_refresh_token = encrypt_token(new_refresh, vault_key)

                # Extend token_expiry
                expires_in = int(refresh_result.get("expires_in", 3600))
                token.token_expiry = datetime.now(tz=timezone.utc) + timedelta(
                    seconds=expires_in
                )

                result["success"] = True

            except Exception as exc:  # noqa: BLE001
                # T-1-21: Log error but continue processing remaining tokens
                logger.error(
                    "Token refresh failed for provider=%s user_id=%s: %s",
                    token.provider,
                    token.user_id,
                    exc,
                )
                result["error"] = str(exc)

            results.append(result)

        await session.commit()

    return results


def _refresh_google_token(
    refresh_token: str,
    client_id: str = "",
    client_secret: str = "",
) -> dict:
    """Refresh a Google OAuth access token using the stored refresh token.

    Uses google.oauth2.credentials.Credentials with the refresh token to
    call Google's token endpoint and obtain a new access token.

    T-1-19: refresh_token is plaintext in-memory only — caller must decrypt
            before passing and encrypt the returned access_token immediately.

    Args:
        refresh_token: Decrypted Google refresh token string.
        client_id: Google OAuth client ID (read from Settings if not provided).
        client_secret: Google OAuth client secret (read from Settings if not provided).

    Returns:
        Dict with access_token, refresh_token (may be None), and expires_in.
    """
    import google.auth.transport.requests
    import google.oauth2.credentials
    from daily.config import Settings

    if not client_id or not client_secret:
        settings = Settings()
        client_id = client_id or settings.google_client_id
        client_secret = client_secret or settings.google_client_secret

    credentials = google.oauth2.credentials.Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
    )

    request = google.auth.transport.requests.Request()
    credentials.refresh(request)

    expires_in = 3600  # Google typically returns 1-hour tokens
    if credentials.expiry:
        delta = credentials.expiry.replace(tzinfo=timezone.utc) - datetime.now(
            tz=timezone.utc
        )
        expires_in = max(int(delta.total_seconds()), 0)

    return {
        "access_token": credentials.token,
        # Pitfall 1: Google only re-issues refresh_token on first consent.
        # credentials.refresh_token contains the (possibly unchanged) refresh token.
        "refresh_token": credentials.refresh_token if credentials.refresh_token != refresh_token else None,
        "expires_in": expires_in,
    }


def _refresh_microsoft_token(
    refresh_token: str,
    client_id: str = "",
    tenant_id: str = "",
    scopes: list[str] | None = None,
) -> dict:
    """Refresh a Microsoft OAuth access token using MSAL.

    Uses msal.PublicClientApplication.acquire_token_by_refresh_token to
    exchange the refresh token for new tokens via Microsoft's token endpoint.

    T-1-19: refresh_token is plaintext in-memory only — caller must decrypt
            before passing and encrypt the returned access_token immediately.

    Args:
        refresh_token: Decrypted Microsoft refresh token string.
        client_id: Azure AD application client ID (read from Settings if not provided).
        tenant_id: Azure AD tenant ID (read from Settings if not provided).
        scopes: OAuth scopes for the new token (defaults to MICROSOFT_READONLY_SCOPES).

    Returns:
        Dict with access_token, refresh_token (may be None), and expires_in.

    Raises:
        ValueError: If MSAL returns an error response.
    """
    import msal

    from daily.config import Settings
    from daily.integrations.microsoft.auth import MICROSOFT_READONLY_SCOPES

    if not client_id or not tenant_id:
        settings = Settings()
        client_id = client_id or settings.microsoft_client_id
        tenant_id = tenant_id or settings.microsoft_tenant_id

    if scopes is None:
        scopes = MICROSOFT_READONLY_SCOPES

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.PublicClientApplication(client_id, authority=authority)

    result = app.acquire_token_by_refresh_token(
        refresh_token,
        scopes=scopes,
    )

    if "error" in result:
        raise ValueError(
            f"Microsoft token refresh error: {result.get('error')} — "
            f"{result.get('error_description', '')}"
        )

    return {
        "access_token": result["access_token"],
        "refresh_token": result.get("refresh_token"),
        "expires_in": result.get("expires_in", 3600),
    }
