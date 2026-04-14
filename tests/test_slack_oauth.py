"""Tests for Slack OAuth flow: scope enforcement and token encryption."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from daily.integrations.slack.auth import (
    SLACK_BOT_SCOPES,
    SLACK_TOKEN_URL,
    store_slack_token,
)


def test_slack_bot_scopes_count():
    """SLACK_BOT_SCOPES has exactly 5 scopes (SEC-03: minimum only)."""
    assert len(SLACK_BOT_SCOPES) == 5


def test_slack_bot_scopes_contains_channels_read():
    """SLACK_BOT_SCOPES includes channels:read."""
    assert "channels:read" in SLACK_BOT_SCOPES


def test_slack_bot_scopes_contains_channels_history():
    """SLACK_BOT_SCOPES includes channels:history."""
    assert "channels:history" in SLACK_BOT_SCOPES


def test_slack_bot_scopes_contains_im_read():
    """SLACK_BOT_SCOPES includes im:read."""
    assert "im:read" in SLACK_BOT_SCOPES


def test_slack_bot_scopes_contains_im_history():
    """SLACK_BOT_SCOPES includes im:history."""
    assert "im:history" in SLACK_BOT_SCOPES


def test_slack_bot_scopes_contains_users_read():
    """SLACK_BOT_SCOPES includes users:read."""
    assert "users:read" in SLACK_BOT_SCOPES


def test_slack_bot_scopes_no_write_scopes():
    """SLACK_BOT_SCOPES does not include any write or post scopes (T-1-13)."""
    for scope in SLACK_BOT_SCOPES:
        assert "write" not in scope
        assert "post" not in scope
        assert "send" not in scope


def test_slack_token_url_is_v2():
    """Token exchange uses Slack OAuth V2 endpoint (oauth.v2.access)."""
    assert "oauth.v2.access" in SLACK_TOKEN_URL


@pytest.mark.asyncio
async def test_store_slack_token_encrypts_bot_token(vault_key):
    """store_slack_token calls encrypt_token on the bot token (T-1-14)."""
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.add = MagicMock()
    mock_session_factory = MagicMock(return_value=mock_session)

    with patch("daily.integrations.slack.auth.encrypt_token") as mock_encrypt:
        mock_encrypt.return_value = "encrypted:xoxb-test-token"
        await store_slack_token(
            bot_token="xoxb-test-token",
            user_id=1,
            vault_key=vault_key,
            session_factory=mock_session_factory,
        )

    mock_encrypt.assert_called_once()
    assert mock_encrypt.call_args.args[0] == "xoxb-test-token"


@pytest.mark.asyncio
async def test_store_slack_token_uses_vault_key(vault_key):
    """store_slack_token passes vault_key to encrypt_token."""
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.add = MagicMock()
    mock_session_factory = MagicMock(return_value=mock_session)

    with patch("daily.integrations.slack.auth.encrypt_token") as mock_encrypt:
        mock_encrypt.return_value = "encrypted:token"
        await store_slack_token(
            bot_token="xoxb-test-token",
            user_id=1,
            vault_key=vault_key,
            session_factory=mock_session_factory,
        )

    assert mock_encrypt.call_args.args[1] == vault_key


@pytest.mark.asyncio
async def test_store_slack_token_writes_provider_slack(vault_key):
    """store_slack_token creates an IntegrationToken with provider='slack'."""
    from daily.db.models import IntegrationToken

    captured_tokens = []

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.add = MagicMock(side_effect=lambda obj: captured_tokens.append(obj))
    mock_session_factory = MagicMock(return_value=mock_session)

    with patch("daily.integrations.slack.auth.encrypt_token") as mock_encrypt:
        mock_encrypt.return_value = "encrypted:token"
        await store_slack_token(
            bot_token="xoxb-test-token",
            user_id=1,
            vault_key=vault_key,
            session_factory=mock_session_factory,
        )

    assert len(captured_tokens) == 1
    token = captured_tokens[0]
    assert isinstance(token, IntegrationToken)
    assert token.provider == "slack"
    assert token.user_id == 1


@pytest.mark.asyncio
async def test_store_slack_token_stores_all_scopes(vault_key):
    """store_slack_token stores all SLACK_BOT_SCOPES in the scopes field."""
    captured_tokens = []

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.add = MagicMock(side_effect=lambda obj: captured_tokens.append(obj))
    mock_session_factory = MagicMock(return_value=mock_session)

    with patch("daily.integrations.slack.auth.encrypt_token") as mock_encrypt:
        mock_encrypt.return_value = "encrypted:token"
        await store_slack_token(
            bot_token="xoxb-test-token",
            user_id=1,
            vault_key=vault_key,
            session_factory=mock_session_factory,
        )

    token = captured_tokens[0]
    stored_scopes = token.scopes.split(" ")
    for scope in SLACK_BOT_SCOPES:
        assert scope in stored_scopes


@pytest.mark.asyncio
async def test_store_slack_token_no_refresh_token(vault_key):
    """store_slack_token stores None for refresh token (Slack bot tokens do not expire)."""
    captured_tokens = []

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.add = MagicMock(side_effect=lambda obj: captured_tokens.append(obj))
    mock_session_factory = MagicMock(return_value=mock_session)

    with patch("daily.integrations.slack.auth.encrypt_token") as mock_encrypt:
        mock_encrypt.return_value = "encrypted:token"
        await store_slack_token(
            bot_token="xoxb-test-token",
            user_id=1,
            vault_key=vault_key,
            session_factory=mock_session_factory,
        )

    token = captured_tokens[0]
    assert token.encrypted_refresh_token is None
    assert token.token_expiry is None
