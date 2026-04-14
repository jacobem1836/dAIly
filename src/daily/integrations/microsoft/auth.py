"""
Microsoft Graph OAuth 2.0 flow with MSAL and localhost callback.

Implements MSAL auth code flow:
- Opens browser to Microsoft's authorization URL
- Spins up a temporary FastAPI server on localhost:8080 to capture the callback
- Exchanges auth code for tokens via MSAL
- Encrypts tokens via vault before writing to DB

SEC-03: Only Mail.Read, Calendars.Read, User.Read, offline_access scopes are requested.
Phase 4 write scopes (Mail.ReadWrite, Calendars.ReadWrite) are deferred.
T-1-17: Only read-only scopes — no write scopes requested.
T-1-18: Tokens encrypted via encrypt_token before DB write — never logged in plaintext.
T-1-20: Redirect URI must match Azure AD registration exactly (no trailing slash).
        MSAL handles PKCE automatically in auth code flow.
"""

import asyncio
import threading
import webbrowser
from datetime import datetime, timedelta, timezone
from typing import Any

import msal
import uvicorn
from fastapi import FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from daily.db.models import IntegrationToken
from daily.vault.crypto import encrypt_token

# SEC-03: Phase 1 minimum readonly scopes only.
# Mail.ReadWrite and Calendars.ReadWrite deferred to Phase 4.
# T-1-17: No write scopes in Phase 1.
MICROSOFT_READONLY_SCOPES = [
    "Mail.Read",
    "Calendars.Read",
    "User.Read",
    "offline_access",
]

# Redirect URI must match Azure AD registration exactly — no trailing slash (Pitfall 3 / T-1-20)
_REDIRECT_URI = "http://localhost:8080/callback"


def run_microsoft_oauth_flow(
    client_id: str,
    tenant_id: str,
    scopes: list[str] | None = None,
    redirect_uri: str = _REDIRECT_URI,
) -> dict[str, Any]:
    """Run Microsoft Graph OAuth 2.0 auth code flow with a temporary localhost callback server.

    Opens the user's browser, spins up a temporary FastAPI server to capture
    the authorization callback, exchanges the code via MSAL, and returns the
    token result dict.

    T-1-20: Redirect URI must match Azure AD registration exactly (no trailing slash).
            MSAL handles PKCE automatically.
    T-1-18: Returned tokens must be encrypted before DB storage.

    Args:
        client_id: Azure AD application (client) ID.
        tenant_id: Azure AD directory (tenant) ID, or "common" for multi-tenant.
        scopes: OAuth scopes to request (defaults to MICROSOFT_READONLY_SCOPES).
        redirect_uri: Callback URI (must match Azure AD configuration exactly).

    Returns:
        MSAL token result dict containing access_token, refresh_token, expires_in.

    Raises:
        RuntimeError: If OAuth flow does not complete within timeout.
        ValueError: If MSAL returns an error response.
    """
    if scopes is None:
        scopes = MICROSOFT_READONLY_SCOPES

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.PublicClientApplication(client_id, authority=authority)

    auth_url = app.get_authorization_request_url(
        scopes=scopes,
        redirect_uri=redirect_uri,
    )

    webbrowser.open(auth_url)

    result_holder: dict[str, Any] = {}
    shutdown_event = threading.Event()

    callback_app = FastAPI()

    @callback_app.get("/callback")
    async def callback(request: Request, code: str, state: str | None = None) -> dict:
        """Capture OAuth authorization code and exchange for tokens via MSAL.

        T-1-20: MSAL handles state validation and PKCE internally.
        """
        token_result = app.acquire_token_by_authorization_code(
            code,
            scopes=scopes,
            redirect_uri=redirect_uri,
        )
        result_holder["result"] = token_result
        shutdown_event.set()
        return {"message": "Authorization successful. You may close this tab."}

    server_config = uvicorn.Config(
        callback_app,
        host="127.0.0.1",
        port=8080,
        log_level="error",
    )
    server = uvicorn.Server(server_config)

    def _watch_and_shutdown() -> None:
        shutdown_event.wait(timeout=300)
        server.should_exit = True

    watcher = threading.Thread(target=_watch_and_shutdown, daemon=True)
    watcher.start()

    server.run()

    if "result" not in result_holder:
        raise RuntimeError(
            "OAuth flow did not complete — no tokens received within timeout."
        )

    result = result_holder["result"]
    if "error" in result:
        raise ValueError(
            f"Microsoft OAuth error: {result.get('error')} — {result.get('error_description', '')}"
        )

    return result


async def store_microsoft_tokens(
    result: dict[str, Any],
    user_id: int,
    vault_key: bytes,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Encrypt and persist Microsoft OAuth tokens to the integration_tokens table.

    T-1-18: Both access_token and refresh_token are encrypted before DB write.
    A single IntegrationToken row covers Outlook mail and calendar since
    they share one Microsoft Graph OAuth grant.

    Args:
        result: MSAL token result dict from run_microsoft_oauth_flow.
        user_id: ID of the user who completed the OAuth flow.
        vault_key: 32-byte AES-256 key from Settings.vault_key.
        session_factory: Async session factory from make_session_factory.
    """
    access_token = result["access_token"]
    refresh_token = result.get("refresh_token")
    expires_in = result.get("expires_in", 3600)

    encrypted_access = encrypt_token(access_token, vault_key)
    encrypted_refresh = (
        encrypt_token(refresh_token, vault_key) if refresh_token else None
    )

    token_expiry = datetime.now(tz=timezone.utc) + timedelta(seconds=int(expires_in))
    scopes_str = " ".join(MICROSOFT_READONLY_SCOPES)

    token_row = IntegrationToken(
        user_id=user_id,
        provider="outlook",
        encrypted_access_token=encrypted_access,
        encrypted_refresh_token=encrypted_refresh,
        token_expiry=token_expiry,
        scopes=scopes_str,
    )

    async with session_factory() as session:
        session.add(token_row)
        await session.commit()
