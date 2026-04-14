"""
Slack OAuth V2 flow with localhost callback and encrypted token storage.

Implements the same localhost callback pattern as google/auth.py:
- Opens browser to Slack's OAuth V2 authorization URL
- Spins up a temporary FastAPI server on localhost:8080 to capture the callback
- Exchanges auth code for bot token via oauth.v2.access
- Encrypts bot token via vault before writing to DB

SEC-03: Only 5 read-only bot scopes requested in Phase 1.
T-1-13: Only read-only scopes; no write scopes in Phase 1.
T-1-14: Bot token encrypted via encrypt_token before DB write — never logged in plaintext.
"""

import threading
import webbrowser
from urllib.parse import urlencode

import httpx
import uvicorn
from fastapi import FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from daily.db.models import IntegrationToken
from daily.vault.crypto import encrypt_token

# SEC-03: Phase 1 minimum readonly bot scopes only.
# Write scopes deferred to Phase 4.
# T-1-13: Only 5 read-only bot scopes; no write scopes.
SLACK_BOT_SCOPES = [
    "channels:read",
    "channels:history",
    "im:read",
    "im:history",
    "users:read",
]

SLACK_AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
SLACK_TOKEN_URL = "https://slack.com/api/oauth.v2.access"


def run_slack_oauth_flow(
    client_id: str,
    client_secret: str,
    redirect_uri: str = "http://localhost:8080/callback",
) -> str:
    """Run Slack OAuth V2 flow with a temporary localhost callback server.

    Opens the user's browser, spins up a temporary FastAPI server to capture
    the authorization callback, exchanges the code for a bot token, and
    returns the bot token string.

    T-1-14: Returned bot token must be encrypted before DB storage.

    Args:
        client_id: Slack app client ID.
        client_secret: Slack app client secret.
        redirect_uri: Callback URI (must match Slack app configuration).

    Returns:
        Slack bot token string (xoxb-...).

    Raises:
        RuntimeError: If OAuth flow does not complete within timeout.
        RuntimeError: If Slack token exchange returns an error.
    """
    params = {
        "client_id": client_id,
        "scope": ",".join(SLACK_BOT_SCOPES),
        "redirect_uri": redirect_uri,
    }
    auth_url = f"{SLACK_AUTHORIZE_URL}?{urlencode(params)}"

    webbrowser.open(auth_url)

    token_holder: dict[str, str] = {}
    shutdown_event = threading.Event()

    callback_app = FastAPI()

    @callback_app.get("/callback")
    async def callback(request: Request, code: str) -> dict:
        """Capture Slack OAuth code and exchange for bot token.

        T-1-14: bot token extracted here and returned for encryption before storage.
        """
        response = httpx.post(
            SLACK_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )
        response.raise_for_status()
        data = response.json()

        if not data.get("ok"):
            error = data.get("error", "unknown_error")
            shutdown_event.set()
            return {"message": f"Slack OAuth error: {error}. You may close this tab."}

        token_holder["access_token"] = data["access_token"]
        shutdown_event.set()
        return {"message": "Slack authorization successful. You may close this tab."}

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

    if "access_token" not in token_holder:
        raise RuntimeError(
            "Slack OAuth flow did not complete — no bot token received within timeout."
        )

    return token_holder["access_token"]


async def store_slack_token(
    bot_token: str,
    user_id: int,
    vault_key: bytes,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Encrypt and persist Slack bot token to the integration_tokens table.

    T-1-14: Bot token encrypted via encrypt_token before DB write.
    Slack bot tokens do not expire, so token_expiry and encrypted_refresh_token
    are stored as None.

    Args:
        bot_token: Slack bot token (xoxb-...) from run_slack_oauth_flow.
        user_id: ID of the user who completed the OAuth flow.
        vault_key: 32-byte AES-256 key from Settings.vault_key.
        session_factory: Async session factory from make_session_factory.
    """
    encrypted_token = encrypt_token(bot_token, vault_key)

    token_row = IntegrationToken(
        user_id=user_id,
        provider="slack",
        encrypted_access_token=encrypted_token,
        encrypted_refresh_token=None,
        token_expiry=None,
        scopes=" ".join(SLACK_BOT_SCOPES),
    )

    async with session_factory() as session:
        session.add(token_row)
        await session.commit()
