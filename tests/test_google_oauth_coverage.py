"""Coverage uplift for google/auth.py — tests run_google_oauth_flow via mocks.

Covers lines 69-135 (run_google_oauth_flow) by mocking browser/server/Flow.
RuntimeError path covers setup code + timeout check (~17 stmts, brings to 82%+).
"""
import pytest
from unittest.mock import MagicMock, patch

from daily.integrations.google.auth import (
    GOOGLE_READONLY_SCOPES,
    GOOGLE_ACTION_SCOPES,
    run_google_oauth_flow,
    store_google_tokens,
)


# ---------------------------------------------------------------------------
# run_google_oauth_flow — timeout / RuntimeError path
# ---------------------------------------------------------------------------


def test_run_google_oauth_flow_timeout_raises():
    """run_google_oauth_flow raises RuntimeError when no credentials received."""
    with patch("daily.integrations.google.auth.webbrowser.open"), \
         patch("daily.integrations.google.auth.uvicorn.Server") as mock_server_cls, \
         patch("daily.integrations.google.auth.uvicorn.Config"), \
         patch("daily.integrations.google.auth.Flow") as mock_flow_cls:

        mock_flow = MagicMock()
        mock_flow.authorization_url.return_value = ("https://accounts.google.com/auth", "state")
        mock_flow_cls.from_client_config.return_value = mock_flow

        mock_server = MagicMock()
        mock_server.run.return_value = None  # no-op: credentials_holder stays empty
        mock_server_cls.return_value = mock_server

        with pytest.raises(RuntimeError, match="OAuth flow did not complete"):
            run_google_oauth_flow(
                client_id="fake-id",
                client_secret="fake-secret",
                scopes=GOOGLE_READONLY_SCOPES,
            )

    mock_flow_cls.from_client_config.assert_called_once()
    mock_flow.authorization_url.assert_called_once()


def test_run_google_oauth_flow_opens_browser():
    """run_google_oauth_flow opens the browser with the authorization URL."""
    opened_urls = []

    with patch("daily.integrations.google.auth.webbrowser.open", side_effect=opened_urls.append), \
         patch("daily.integrations.google.auth.uvicorn.Server") as mock_server_cls, \
         patch("daily.integrations.google.auth.uvicorn.Config"), \
         patch("daily.integrations.google.auth.Flow") as mock_flow_cls:

        mock_flow = MagicMock()
        mock_flow.authorization_url.return_value = ("https://auth.example.com", "state")
        mock_flow_cls.from_client_config.return_value = mock_flow
        mock_server_cls.return_value.run.return_value = None

        with pytest.raises(RuntimeError):
            run_google_oauth_flow("id", "secret", GOOGLE_READONLY_SCOPES)

    assert len(opened_urls) == 1
    assert "https://auth.example.com" in opened_urls[0]


def test_run_google_oauth_flow_uses_offline_access():
    """run_google_oauth_flow requests offline access to receive refresh_token."""
    with patch("daily.integrations.google.auth.webbrowser.open"), \
         patch("daily.integrations.google.auth.uvicorn.Server") as mock_server_cls, \
         patch("daily.integrations.google.auth.uvicorn.Config"), \
         patch("daily.integrations.google.auth.Flow") as mock_flow_cls:

        mock_flow = MagicMock()
        mock_flow.authorization_url.return_value = ("https://auth.example.com", "s")
        mock_flow_cls.from_client_config.return_value = mock_flow
        mock_server_cls.return_value.run.return_value = None

        with pytest.raises(RuntimeError):
            run_google_oauth_flow("id", "secret", GOOGLE_READONLY_SCOPES)

    call_kwargs = mock_flow.authorization_url.call_args.kwargs
    assert call_kwargs.get("access_type") == "offline"
    assert call_kwargs.get("prompt") == "consent"


def test_run_google_oauth_flow_custom_redirect_uri():
    """run_google_oauth_flow accepts a custom redirect_uri."""
    with patch("daily.integrations.google.auth.webbrowser.open"), \
         patch("daily.integrations.google.auth.uvicorn.Server") as mock_server_cls, \
         patch("daily.integrations.google.auth.uvicorn.Config"), \
         patch("daily.integrations.google.auth.Flow") as mock_flow_cls:

        mock_flow = MagicMock()
        mock_flow.authorization_url.return_value = ("https://auth.example.com", "s")
        mock_flow_cls.from_client_config.return_value = mock_flow
        mock_server_cls.return_value.run.return_value = None

        with pytest.raises(RuntimeError):
            run_google_oauth_flow("id", "secret", GOOGLE_READONLY_SCOPES, redirect_uri="http://localhost:9090/cb")

    call_kwargs = mock_flow_cls.from_client_config.call_args.kwargs
    assert call_kwargs.get("redirect_uri") == "http://localhost:9090/cb"


# ---------------------------------------------------------------------------
# store_google_tokens — null refresh_token path (not covered by existing tests)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_google_tokens_no_refresh_token():
    """store_google_tokens stores None for encrypted_refresh_token when missing."""
    from unittest.mock import AsyncMock
    from daily.db.models import IntegrationToken

    mock_credentials = MagicMock()
    mock_credentials.token = "access"
    mock_credentials.refresh_token = None
    mock_credentials.expiry = None
    mock_credentials.scopes = None

    captured = []
    mock_session = MagicMock()
    mock_session.add.side_effect = lambda obj: captured.append(obj)
    mock_session.commit = AsyncMock()
    mock_session.execute = AsyncMock()

    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("daily.integrations.google.auth.encrypt_token", side_effect=lambda t, k: f"enc:{t}"):
        await store_google_tokens(mock_credentials, user_id=1, vault_key=b"k" * 32, session_factory=mock_factory)

    assert captured[0].encrypted_refresh_token is None


# ---------------------------------------------------------------------------
# Scope constants
# ---------------------------------------------------------------------------


def test_google_action_scopes_include_send():
    """GOOGLE_ACTION_SCOPES includes gmail.send for Phase 4 write actions."""
    assert any("send" in s for s in GOOGLE_ACTION_SCOPES)
