"""
Tests for cross-provider token refresh logic.

Tests cover:
- Identification of tokens expiring within buffer_minutes
- Skipping tokens with no token_expiry (Slack bot tokens)
- Skipping tokens not yet near expiry
- Google token refresh via google.oauth2 credentials
- Microsoft token refresh via MSAL acquire_token_by_refresh_token
- Re-encryption of new access tokens after successful refresh
- Graceful error handling (one failed refresh does not block others)

All tests use in-memory mocks — no live DB or API calls.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from daily.vault.refresh import refresh_expiring_tokens


def _make_token_row(
    *,
    provider: str = "google",
    token_expiry: datetime | None = None,
    encrypted_access_token: str = "enc_access",
    encrypted_refresh_token: str | None = "enc_refresh",
    scopes: str = "https://www.googleapis.com/auth/gmail.readonly",
    user_id: int = 1,
    id: int = 1,
) -> MagicMock:
    """Build a mock IntegrationToken ORM row."""
    row = MagicMock()
    row.id = id
    row.user_id = user_id
    row.provider = provider
    row.token_expiry = token_expiry
    row.encrypted_access_token = encrypted_access_token
    row.encrypted_refresh_token = encrypted_refresh_token
    row.scopes = scopes
    return row


def _make_session_factory(token_rows: list) -> MagicMock:
    """Build a mock async session factory that returns given token rows on scalars().all()."""
    mock_result = MagicMock()
    mock_result.all.return_value = token_rows

    mock_scalars_result = MagicMock()
    mock_scalars_result.all.return_value = token_rows

    mock_session = MagicMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.scalars = AsyncMock(return_value=mock_scalars_result)
    mock_session.commit = AsyncMock()

    # For the execute result used to get rows
    mock_result.scalars.return_value = mock_scalars_result

    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_session_factory


class TestRefreshExpiringTokensIdentifiesNearExpiry:
    @pytest.mark.asyncio
    async def test_identifies_token_expiring_within_buffer(self):
        """Tokens with expiry within buffer_minutes must be refreshed."""
        near_expiry = datetime.now(tz=timezone.utc) + timedelta(minutes=5)
        token = _make_token_row(provider="google", token_expiry=near_expiry)

        session_factory = _make_session_factory([token])
        vault_key = b"k" * 32

        with (
            patch("daily.vault.refresh.decrypt_token", return_value="plain_refresh"),
            patch("daily.vault.refresh.encrypt_token", return_value="new_enc_access"),
            patch("daily.vault.refresh._refresh_google_token") as mock_google_refresh,
        ):
            mock_google_refresh.return_value = {
                "access_token": "new_access",
                "refresh_token": None,
                "expires_in": 3600,
            }
            results = await refresh_expiring_tokens(session_factory, vault_key)

        assert any(r["provider"] == "google" for r in results)
        mock_google_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_token_not_near_expiry(self):
        """Tokens with expiry > buffer_minutes from now must NOT be refreshed."""
        far_expiry = datetime.now(tz=timezone.utc) + timedelta(hours=2)
        token = _make_token_row(provider="google", token_expiry=far_expiry)

        session_factory = _make_session_factory([token])
        vault_key = b"k" * 32

        with patch("daily.vault.refresh._refresh_google_token") as mock_google_refresh:
            results = await refresh_expiring_tokens(session_factory, vault_key)

        # Far-expiry token must not trigger a refresh
        mock_google_refresh.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_slack_token_with_no_expiry(self):
        """Slack bot tokens have no expiry and must be skipped (T-1-21 / INTG-05)."""
        slack_token = _make_token_row(
            provider="slack",
            token_expiry=None,  # Slack bot tokens never expire
        )

        session_factory = _make_session_factory([slack_token])
        vault_key = b"k" * 32

        with patch("daily.vault.refresh._refresh_google_token") as mock_google:
            with patch("daily.vault.refresh._refresh_microsoft_token") as mock_ms:
                results = await refresh_expiring_tokens(session_factory, vault_key)

        mock_google.assert_not_called()
        mock_ms.assert_not_called()


class TestGoogleTokenRefresh:
    @pytest.mark.asyncio
    async def test_google_refresh_updates_access_token(self):
        """After Google token refresh, encrypted_access_token must be updated."""
        near_expiry = datetime.now(tz=timezone.utc) + timedelta(minutes=5)
        token = _make_token_row(
            provider="google",
            token_expiry=near_expiry,
            encrypted_access_token="old_enc_access",
            encrypted_refresh_token="enc_refresh",
        )

        session_factory = _make_session_factory([token])
        vault_key = b"k" * 32

        with (
            patch("daily.vault.refresh.decrypt_token", return_value="plain_refresh"),
            patch("daily.vault.refresh.encrypt_token", return_value="new_enc_access") as mock_encrypt,
            patch("daily.vault.refresh._refresh_google_token") as mock_google_refresh,
        ):
            mock_google_refresh.return_value = {
                "access_token": "new_google_access",
                "refresh_token": None,
                "expires_in": 3600,
            }
            await refresh_expiring_tokens(session_factory, vault_key)

        # encrypt_token must be called with the new access token
        encrypt_calls = [c.args[0] for c in mock_encrypt.call_args_list]
        assert "new_google_access" in encrypt_calls
        # Token row must be updated
        assert token.encrypted_access_token == "new_enc_access"

    @pytest.mark.asyncio
    async def test_google_refresh_result_is_success(self):
        """Successful Google refresh must return success=True in results."""
        near_expiry = datetime.now(tz=timezone.utc) + timedelta(minutes=5)
        token = _make_token_row(provider="google", token_expiry=near_expiry)

        session_factory = _make_session_factory([token])
        vault_key = b"k" * 32

        with (
            patch("daily.vault.refresh.decrypt_token", return_value="plain_refresh"),
            patch("daily.vault.refresh.encrypt_token", return_value="new_enc"),
            patch("daily.vault.refresh._refresh_google_token") as mock_google_refresh,
        ):
            mock_google_refresh.return_value = {
                "access_token": "new_access",
                "refresh_token": None,
                "expires_in": 3600,
            }
            results = await refresh_expiring_tokens(session_factory, vault_key)

        google_result = next(r for r in results if r["provider"] == "google")
        assert google_result["success"] is True


class TestMicrosoftTokenRefresh:
    @pytest.mark.asyncio
    async def test_microsoft_refresh_updates_access_token(self):
        """After Microsoft token refresh, encrypted_access_token must be updated."""
        near_expiry = datetime.now(tz=timezone.utc) + timedelta(minutes=10)
        token = _make_token_row(
            provider="outlook",
            token_expiry=near_expiry,
            encrypted_access_token="old_ms_enc",
            encrypted_refresh_token="enc_ms_refresh",
            scopes="Mail.Read Calendars.Read User.Read offline_access",
        )

        session_factory = _make_session_factory([token])
        vault_key = b"k" * 32

        with (
            patch("daily.vault.refresh.decrypt_token", return_value="plain_ms_refresh"),
            patch("daily.vault.refresh.encrypt_token", return_value="new_ms_enc") as mock_encrypt,
            patch("daily.vault.refresh._refresh_microsoft_token") as mock_ms_refresh,
        ):
            mock_ms_refresh.return_value = {
                "access_token": "new_ms_access",
                "refresh_token": "new_ms_refresh",
                "expires_in": 3600,
            }
            await refresh_expiring_tokens(session_factory, vault_key)

        encrypt_calls = [c.args[0] for c in mock_encrypt.call_args_list]
        assert "new_ms_access" in encrypt_calls
        assert token.encrypted_access_token == "new_ms_enc"

    @pytest.mark.asyncio
    async def test_microsoft_refresh_result_is_success(self):
        """Successful Microsoft refresh must return success=True in results."""
        near_expiry = datetime.now(tz=timezone.utc) + timedelta(minutes=5)
        token = _make_token_row(
            provider="outlook",
            token_expiry=near_expiry,
            scopes="Mail.Read Calendars.Read",
        )

        session_factory = _make_session_factory([token])
        vault_key = b"k" * 32

        with (
            patch("daily.vault.refresh.decrypt_token", return_value="plain_refresh"),
            patch("daily.vault.refresh.encrypt_token", return_value="new_enc"),
            patch("daily.vault.refresh._refresh_microsoft_token") as mock_ms_refresh,
        ):
            mock_ms_refresh.return_value = {
                "access_token": "new_access",
                "refresh_token": None,
                "expires_in": 3600,
            }
            results = await refresh_expiring_tokens(session_factory, vault_key)

        ms_result = next(r for r in results if r["provider"] == "outlook")
        assert ms_result["success"] is True


class TestGracefulErrorHandling:
    @pytest.mark.asyncio
    async def test_failed_refresh_does_not_crash(self):
        """A failed refresh must be caught and logged, not re-raised (T-1-21)."""
        near_expiry = datetime.now(tz=timezone.utc) + timedelta(minutes=5)
        token = _make_token_row(provider="google", token_expiry=near_expiry)

        session_factory = _make_session_factory([token])
        vault_key = b"k" * 32

        with (
            patch("daily.vault.refresh.decrypt_token", return_value="plain_refresh"),
            patch(
                "daily.vault.refresh._refresh_google_token",
                side_effect=Exception("Network error"),
            ),
        ):
            # Must not raise — graceful degradation
            results = await refresh_expiring_tokens(session_factory, vault_key)

        google_result = next(r for r in results if r["provider"] == "google")
        assert google_result["success"] is False
        assert "error" in google_result
        assert google_result["error"] is not None

    @pytest.mark.asyncio
    async def test_one_failure_does_not_block_others(self):
        """If one token refresh fails, the rest must still be attempted (T-1-21)."""
        near_expiry = datetime.now(tz=timezone.utc) + timedelta(minutes=5)
        google_token = _make_token_row(
            id=1, provider="google", token_expiry=near_expiry
        )
        ms_token = _make_token_row(
            id=2,
            provider="outlook",
            token_expiry=near_expiry,
            scopes="Mail.Read Calendars.Read",
        )

        session_factory = _make_session_factory([google_token, ms_token])
        vault_key = b"k" * 32

        with (
            patch("daily.vault.refresh.decrypt_token", return_value="plain_refresh"),
            patch("daily.vault.refresh.encrypt_token", return_value="new_enc"),
            patch(
                "daily.vault.refresh._refresh_google_token",
                side_effect=Exception("Google down"),
            ),
            patch("daily.vault.refresh._refresh_microsoft_token") as mock_ms_refresh,
        ):
            mock_ms_refresh.return_value = {
                "access_token": "new_ms_access",
                "refresh_token": None,
                "expires_in": 3600,
            }
            results = await refresh_expiring_tokens(session_factory, vault_key)

        # Both tokens must have result entries
        assert len(results) == 2
        google_result = next(r for r in results if r["provider"] == "google")
        ms_result = next(r for r in results if r["provider"] == "outlook")
        assert google_result["success"] is False
        assert ms_result["success"] is True
