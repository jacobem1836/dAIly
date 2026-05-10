"""Unit tests for vault/refresh.py token-refresh helper functions.

Tests _refresh_google_token and _refresh_microsoft_token with mocked
external clients. Does not make real OAuth network calls.
"""
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# _refresh_google_token
# ---------------------------------------------------------------------------


class TestRefreshGoogleToken:
    """Tests for _refresh_google_token (mocks google.oauth2.credentials)."""

    def _make_credentials(self, token="new_access_token", refresh_token=None, expiry=None):
        creds = MagicMock()
        creds.token = token
        creds.refresh_token = refresh_token
        creds.expiry = expiry
        return creds

    def test_returns_access_token(self):
        """_refresh_google_token returns a dict with access_token."""
        from daily.vault.refresh import _refresh_google_token

        creds = self._make_credentials(token="fresh_access_token")

        with (
            patch("google.oauth2.credentials.Credentials", return_value=creds),
            patch("google.auth.transport.requests.Request"),
        ):
            result = _refresh_google_token("old_refresh_token", "client_id", "client_secret")

        assert result["access_token"] == "fresh_access_token"

    def test_returns_none_refresh_token_when_unchanged(self):
        """If Google returns same refresh_token, result refresh_token is None."""
        from daily.vault.refresh import _refresh_google_token

        same_refresh = "original_refresh_token"
        creds = self._make_credentials(token="new_token", refresh_token=same_refresh)

        with (
            patch("google.oauth2.credentials.Credentials", return_value=creds),
            patch("google.auth.transport.requests.Request"),
        ):
            result = _refresh_google_token(same_refresh, "client_id", "client_secret")

        assert result["refresh_token"] is None

    def test_returns_new_refresh_token_when_changed(self):
        """If Google issues a new refresh_token, it is returned."""
        from daily.vault.refresh import _refresh_google_token

        creds = self._make_credentials(token="new_token", refresh_token="new_refresh_token")

        with (
            patch("google.oauth2.credentials.Credentials", return_value=creds),
            patch("google.auth.transport.requests.Request"),
        ):
            result = _refresh_google_token("old_refresh_token", "client_id", "client_secret")

        assert result["refresh_token"] == "new_refresh_token"

    def test_uses_settings_when_no_client_id(self, monkeypatch):
        """Falls back to Settings when client_id not provided."""
        from daily.vault.refresh import _refresh_google_token

        monkeypatch.setenv("GOOGLE_CLIENT_ID", "settings_client_id")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "settings_client_secret")

        creds = self._make_credentials(token="tok")

        with (
            patch("google.oauth2.credentials.Credentials", return_value=creds),
            patch("google.auth.transport.requests.Request"),
        ):
            result = _refresh_google_token("refresh")

        assert "access_token" in result

    def test_expires_in_computed_from_expiry(self):
        """expires_in is computed from credentials.expiry when present."""
        from daily.vault.refresh import _refresh_google_token
        from datetime import datetime, timedelta, timezone

        future = datetime.now(tz=timezone.utc) + timedelta(seconds=3600)
        creds = self._make_credentials(token="tok", expiry=future)

        with (
            patch("google.oauth2.credentials.Credentials", return_value=creds),
            patch("google.auth.transport.requests.Request"),
        ):
            result = _refresh_google_token("refresh", "cid", "csecret")

        assert result["expires_in"] > 0
        assert result["expires_in"] <= 3600

    def test_expires_in_defaults_when_no_expiry(self):
        """expires_in defaults to 3600 when credentials.expiry is None."""
        from daily.vault.refresh import _refresh_google_token

        creds = self._make_credentials(token="tok", expiry=None)

        with (
            patch("google.oauth2.credentials.Credentials", return_value=creds),
            patch("google.auth.transport.requests.Request"),
        ):
            result = _refresh_google_token("refresh", "cid", "csecret")

        assert result["expires_in"] == 3600


# ---------------------------------------------------------------------------
# _refresh_microsoft_token
# ---------------------------------------------------------------------------


class TestRefreshMicrosoftToken:
    """Tests for _refresh_microsoft_token (mocks msal)."""

    def _make_msal_app(self, access_token="new_access_token", new_refresh=None, error=None):
        app = MagicMock()
        if error:
            result = {"error": error, "error_description": "Test error"}
        else:
            result = {
                "access_token": access_token,
                "expires_in": 3600,
            }
            if new_refresh:
                result["refresh_token"] = new_refresh
        app.acquire_token_by_refresh_token.return_value = result
        return app

    def test_returns_access_token(self):
        """_refresh_microsoft_token returns a dict with access_token."""
        from daily.vault.refresh import _refresh_microsoft_token

        app = self._make_msal_app(access_token="ms_access_token")

        with patch("msal.PublicClientApplication", return_value=app):
            result = _refresh_microsoft_token(
                "old_refresh", "client_id", "tenant_id", scopes=["scope1"]
            )

        assert result["access_token"] == "ms_access_token"

    def test_raises_on_error_response(self):
        """_refresh_microsoft_token raises ValueError on MSAL error."""
        from daily.vault.refresh import _refresh_microsoft_token

        app = self._make_msal_app(error="invalid_grant")

        with patch("msal.PublicClientApplication", return_value=app):
            with pytest.raises(ValueError, match="Microsoft token refresh error"):
                _refresh_microsoft_token("bad_refresh", "cid", "tid", scopes=[])

    def test_returns_none_refresh_token_when_not_in_response(self):
        """refresh_token is None when not returned by MSAL."""
        from daily.vault.refresh import _refresh_microsoft_token

        app = self._make_msal_app(access_token="tok")  # no new refresh token

        with patch("msal.PublicClientApplication", return_value=app):
            result = _refresh_microsoft_token("old_refresh", "cid", "tid", scopes=[])

        assert result["refresh_token"] is None

    def test_returns_new_refresh_token(self):
        """refresh_token is returned when MSAL issues one."""
        from daily.vault.refresh import _refresh_microsoft_token

        app = self._make_msal_app(access_token="tok", new_refresh="new_ms_refresh")

        with patch("msal.PublicClientApplication", return_value=app):
            result = _refresh_microsoft_token("old_refresh", "cid", "tid", scopes=["s1"])

        assert result["refresh_token"] == "new_ms_refresh"

    def test_uses_settings_when_no_client_id(self, monkeypatch):
        """Falls back to Settings when client_id/tenant_id not provided."""
        from daily.vault.refresh import _refresh_microsoft_token

        monkeypatch.setenv("MICROSOFT_CLIENT_ID", "ms_client_id")
        monkeypatch.setenv("MICROSOFT_TENANT_ID", "ms_tenant_id")

        app = self._make_msal_app(access_token="tok")

        with patch("msal.PublicClientApplication", return_value=app):
            result = _refresh_microsoft_token("refresh")

        assert "access_token" in result

    def test_expires_in_defaults_to_3600(self):
        """expires_in defaults to 3600 when not in MSAL response."""
        from daily.vault.refresh import _refresh_microsoft_token

        app = MagicMock()
        app.acquire_token_by_refresh_token.return_value = {
            "access_token": "tok",
            # no expires_in key
        }

        with patch("msal.PublicClientApplication", return_value=app):
            result = _refresh_microsoft_token("refresh", "cid", "tid", scopes=[])

        assert result["expires_in"] == 3600
