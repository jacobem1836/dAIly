"""Tests for Google OAuth flow: scope enforcement and token encryption."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from daily.integrations.google.auth import (
    GOOGLE_READONLY_SCOPES,
    store_google_tokens,
)


def test_google_readonly_scopes_contains_gmail():
    """GOOGLE_READONLY_SCOPES includes gmail.readonly."""
    assert "https://www.googleapis.com/auth/gmail.readonly" in GOOGLE_READONLY_SCOPES


def test_google_readonly_scopes_contains_calendar():
    """GOOGLE_READONLY_SCOPES includes calendar.readonly."""
    assert "https://www.googleapis.com/auth/calendar.readonly" in GOOGLE_READONLY_SCOPES


def test_google_readonly_scopes_count():
    """GOOGLE_READONLY_SCOPES has exactly 2 scopes (SEC-03: minimum only)."""
    assert len(GOOGLE_READONLY_SCOPES) == 2


def test_google_readonly_scopes_no_broad_gmail():
    """GOOGLE_READONLY_SCOPES does not include the overly broad https://mail.google.com/ scope."""
    assert "https://mail.google.com/" not in GOOGLE_READONLY_SCOPES


def test_google_readonly_scopes_no_write_scopes():
    """GOOGLE_READONLY_SCOPES does not include any write scopes (Phase 1 read-only)."""
    for scope in GOOGLE_READONLY_SCOPES:
        assert "compose" not in scope
        assert "modify" not in scope
        assert "send" not in scope
        assert "calendar.events" == scope.split("/")[-1] or "readonly" in scope


@pytest.mark.asyncio
async def test_store_google_tokens_encrypts_access_token(vault_key):
    """store_google_tokens calls encrypt_token on the access_token."""
    mock_credentials = MagicMock()
    mock_credentials.token = "test_access_token"
    mock_credentials.refresh_token = "test_refresh_token"
    mock_credentials.expiry = None
    mock_credentials.scopes = GOOGLE_READONLY_SCOPES

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session_factory = MagicMock(return_value=mock_session)

    with patch("daily.integrations.google.auth.encrypt_token") as mock_encrypt:
        mock_encrypt.side_effect = lambda plaintext, key: f"encrypted:{plaintext}"
        await store_google_tokens(
            credentials=mock_credentials,
            user_id=1,
            vault_key=vault_key,
            session_factory=mock_session_factory,
        )

    # encrypt_token called at least twice: access_token + refresh_token
    assert mock_encrypt.call_count >= 2
    call_args = [call.args[0] for call in mock_encrypt.call_args_list]
    assert "test_access_token" in call_args
    assert "test_refresh_token" in call_args


@pytest.mark.asyncio
async def test_store_google_tokens_uses_vault_key(vault_key):
    """store_google_tokens passes vault_key to encrypt_token."""
    mock_credentials = MagicMock()
    mock_credentials.token = "access"
    mock_credentials.refresh_token = "refresh"
    mock_credentials.expiry = None
    mock_credentials.scopes = GOOGLE_READONLY_SCOPES

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session_factory = MagicMock(return_value=mock_session)

    with patch("daily.integrations.google.auth.encrypt_token") as mock_encrypt:
        mock_encrypt.side_effect = lambda plaintext, key: f"enc:{plaintext}"
        await store_google_tokens(
            credentials=mock_credentials,
            user_id=1,
            vault_key=vault_key,
            session_factory=mock_session_factory,
        )

    for call in mock_encrypt.call_args_list:
        assert call.args[1] == vault_key


@pytest.mark.asyncio
async def test_store_google_tokens_writes_provider_google(vault_key):
    """store_google_tokens creates an IntegrationToken with provider='google'."""
    from daily.db.models import IntegrationToken

    mock_credentials = MagicMock()
    mock_credentials.token = "access"
    mock_credentials.refresh_token = "refresh"
    mock_credentials.expiry = None
    mock_credentials.scopes = GOOGLE_READONLY_SCOPES

    captured_tokens = []

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.add = MagicMock(side_effect=lambda obj: captured_tokens.append(obj))
    mock_session_factory = MagicMock(return_value=mock_session)

    with patch("daily.integrations.google.auth.encrypt_token") as mock_encrypt:
        mock_encrypt.side_effect = lambda plaintext, key: f"enc:{plaintext}"
        await store_google_tokens(
            credentials=mock_credentials,
            user_id=1,
            vault_key=vault_key,
            session_factory=mock_session_factory,
        )

    assert len(captured_tokens) == 1
    token = captured_tokens[0]
    assert isinstance(token, IntegrationToken)
    assert token.provider == "google"
    assert token.user_id == 1
