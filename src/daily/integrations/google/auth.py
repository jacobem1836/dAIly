"""
Google OAuth 2.0 flow with localhost callback and encrypted token storage.

Implements Pattern 3 (OAuth Callback Server) from Phase 1 research:
- Opens browser to Google's authorization URL
- Spins up a temporary FastAPI server on localhost:8080 to capture the callback
- Exchanges auth code for tokens
- Encrypts tokens via vault before writing to DB

SEC-03: Only gmail.readonly and calendar.readonly scopes are requested in Phase 1.
Compose/events write scopes are deferred to Phase 4.
T-1-11: Tokens are encrypted via encrypt_token before DB write — never logged in plaintext.
"""

import asyncio
import os
import threading
import webbrowser
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from google_auth_oauthlib.flow import Flow
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from daily.db.models import IntegrationToken
from daily.vault.crypto import encrypt_token

# SEC-03: Phase 1 minimum readonly scopes only.
GOOGLE_READONLY_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]

# Phase 4: read + write scopes for action layer.
GOOGLE_ACTION_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]


def run_google_oauth_flow(
    client_id: str,
    client_secret: str,
    scopes: list[str],
    redirect_uri: str = "http://localhost:8080/callback",
) -> Any:
    """Run Google OAuth 2.0 flow with a temporary localhost callback server.

    Opens the user's browser, spins up a temporary FastAPI server to capture
    the authorization callback, and returns the Google credentials object.

    T-1-08: OAuth state parameter is validated on callback by the Flow object.
    T-1-11: Returned credentials must be encrypted before DB storage.

    Args:
        client_id: Google OAuth 2.0 client ID.
        client_secret: Google OAuth 2.0 client secret.
        scopes: OAuth scopes to request (use GOOGLE_READONLY_SCOPES for Phase 1).
        redirect_uri: Callback URI (must match Google Cloud Console configuration).

    Returns:
        google.oauth2.credentials.Credentials object with access_token,
        refresh_token, and expiry.
    """
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": [redirect_uri],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=scopes,
        redirect_uri=redirect_uri,
    )

    auth_url, _state = flow.authorization_url(
        access_type="offline",  # Pitfall 1: required to receive refresh_token
        prompt="consent",  # Pitfall 1: force consent screen so refresh_token is always issued
        include_granted_scopes="true",
    )

    # Allow HTTP localhost callback during local development.
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

    webbrowser.open(auth_url)

    credentials_holder: dict[str, Any] = {}
    shutdown_event = threading.Event()

    callback_app = FastAPI()

    @callback_app.get("/callback")
    async def callback(request: Request, code: str, state: str | None = None) -> dict:
        """Capture OAuth authorization code and exchange for tokens.

        T-1-08: state parameter validated by Flow.fetch_token internally.
        """
        authorization_response = str(request.url)
        flow.fetch_token(authorization_response=authorization_response)
        credentials_holder["credentials"] = flow.credentials
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

    if "credentials" not in credentials_holder:
        raise RuntimeError(
            "OAuth flow did not complete — no credentials received within timeout."
        )

    return credentials_holder["credentials"]


async def store_google_tokens(
    credentials: Any,
    user_id: int,
    vault_key: bytes,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Encrypt and persist Google OAuth tokens to the integration_tokens table.

    T-1-11: Both access_token and refresh_token are encrypted before DB write.
    A single IntegrationToken row covers both Gmail and Google Calendar since
    they share one OAuth grant (D-03).

    Args:
        credentials: Google credentials object from run_google_oauth_flow.
        user_id: ID of the user who completed the OAuth flow.
        vault_key: 32-byte AES-256 key from Settings.vault_key.
        session_factory: Async session factory from make_session_factory.
    """
    encrypted_access = encrypt_token(credentials.token, vault_key)
    encrypted_refresh = (
        encrypt_token(credentials.refresh_token, vault_key)
        if credentials.refresh_token
        else None
    )

    scopes_str = " ".join(credentials.scopes) if credentials.scopes else " ".join(GOOGLE_READONLY_SCOPES)

    token_row = IntegrationToken(
        user_id=user_id,
        provider="google",
        encrypted_access_token=encrypted_access,
        encrypted_refresh_token=encrypted_refresh,
        token_expiry=credentials.expiry,
        scopes=scopes_str,
    )

    async with session_factory() as session:
        session.add(token_row)
        await session.commit()
