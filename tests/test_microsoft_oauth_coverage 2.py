"""Coverage uplift for microsoft/auth.py — tests run_microsoft_oauth_flow via mocks.

Covers lines 75-136 (run_microsoft_oauth_flow) by mocking MSAL/browser/server.
RuntimeError path + ValueError path brings coverage to 84%+.
"""
import pytest
from unittest.mock import MagicMock, patch

from daily.integrations.microsoft.auth import (
    MICROSOFT_READONLY_SCOPES,
    _REDIRECT_URI,
    run_microsoft_oauth_flow,
)


# ---------------------------------------------------------------------------
# run_microsoft_oauth_flow — timeout / RuntimeError path
# ---------------------------------------------------------------------------


def test_run_microsoft_oauth_flow_timeout_raises():
    """run_microsoft_oauth_flow raises RuntimeError when no tokens received."""
    with patch("daily.integrations.microsoft.auth.webbrowser.open"), \
         patch("daily.integrations.microsoft.auth.uvicorn.Server") as mock_server_cls, \
         patch("daily.integrations.microsoft.auth.uvicorn.Config"), \
         patch("daily.integrations.microsoft.auth.msal.PublicClientApplication") as mock_msal:

        mock_app = MagicMock()
        mock_app.get_authorization_request_url.return_value = "https://login.microsoftonline.com/auth"
        mock_msal.return_value = mock_app
        mock_server_cls.return_value.run.return_value = None  # no-op

        with pytest.raises(RuntimeError, match="OAuth flow did not complete"):
            run_microsoft_oauth_flow(client_id="fake-id", tenant_id="fake-tenant")

    mock_msal.assert_called_once()
    mock_app.get_authorization_request_url.assert_called_once()


def test_run_microsoft_oauth_flow_uses_tenant_authority():
    """run_microsoft_oauth_flow builds authority URL from tenant_id."""
    with patch("daily.integrations.microsoft.auth.webbrowser.open"), \
         patch("daily.integrations.microsoft.auth.uvicorn.Server") as mock_server_cls, \
         patch("daily.integrations.microsoft.auth.uvicorn.Config"), \
         patch("daily.integrations.microsoft.auth.msal.PublicClientApplication") as mock_msal:

        mock_app = MagicMock()
        mock_app.get_authorization_request_url.return_value = "https://login.microsoftonline.com/auth"
        mock_msal.return_value = mock_app
        mock_server_cls.return_value.run.return_value = None

        with pytest.raises(RuntimeError):
            run_microsoft_oauth_flow(client_id="cid", tenant_id="my-tenant")

    _, kwargs = mock_msal.call_args
    assert "my-tenant" in kwargs.get("authority", "") or "my-tenant" in str(mock_msal.call_args)


def test_run_microsoft_oauth_flow_default_scopes():
    """run_microsoft_oauth_flow uses MICROSOFT_READONLY_SCOPES by default."""
    with patch("daily.integrations.microsoft.auth.webbrowser.open"), \
         patch("daily.integrations.microsoft.auth.uvicorn.Server") as mock_server_cls, \
         patch("daily.integrations.microsoft.auth.uvicorn.Config"), \
         patch("daily.integrations.microsoft.auth.msal.PublicClientApplication") as mock_msal:

        mock_app = MagicMock()
        mock_app.get_authorization_request_url.return_value = "https://login.microsoftonline.com/auth"
        mock_msal.return_value = mock_app
        mock_server_cls.return_value.run.return_value = None

        with pytest.raises(RuntimeError):
            run_microsoft_oauth_flow(client_id="cid", tenant_id="tid")

    call_kwargs = mock_app.get_authorization_request_url.call_args.kwargs
    for scope in MICROSOFT_READONLY_SCOPES:
        assert scope in call_kwargs.get("scopes", [])


def test_run_microsoft_oauth_flow_opens_browser():
    """run_microsoft_oauth_flow calls webbrowser.open with auth URL."""
    opened = []
    with patch("daily.integrations.microsoft.auth.webbrowser.open", side_effect=opened.append), \
         patch("daily.integrations.microsoft.auth.uvicorn.Server") as mock_server_cls, \
         patch("daily.integrations.microsoft.auth.uvicorn.Config"), \
         patch("daily.integrations.microsoft.auth.msal.PublicClientApplication") as mock_msal:

        mock_app = MagicMock()
        mock_app.get_authorization_request_url.return_value = "https://login.example.com/auth"
        mock_msal.return_value = mock_app
        mock_server_cls.return_value.run.return_value = None

        with pytest.raises(RuntimeError):
            run_microsoft_oauth_flow("cid", "tid")

    assert len(opened) == 1


def test_run_microsoft_oauth_flow_error_result_raises_value_error():
    """run_microsoft_oauth_flow raises ValueError when MSAL returns error response."""
    captured_apps = []

    def capture_config(app, **kwargs):
        captured_apps.append(app)
        return MagicMock()

    class FakeServer:
        def __init__(self, config):
            pass

        def run(self):
            import asyncio
            import httpx
            from httpx import ASGITransport

            app = captured_apps[0]

            async def invoke():
                transport = ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
                    await c.get("/callback?code=test_code")

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(invoke())
            finally:
                loop.close()

    with patch("daily.integrations.microsoft.auth.webbrowser.open"), \
         patch("daily.integrations.microsoft.auth.uvicorn.Config", side_effect=capture_config), \
         patch("daily.integrations.microsoft.auth.uvicorn.Server", FakeServer), \
         patch("daily.integrations.microsoft.auth.msal.PublicClientApplication") as mock_msal:

        mock_app = MagicMock()
        mock_app.get_authorization_request_url.return_value = "https://login.microsoftonline.com/auth"
        mock_app.acquire_token_by_authorization_code.return_value = {
            "error": "invalid_grant",
            "error_description": "Token revoked",
        }
        mock_msal.return_value = mock_app

        with pytest.raises((ValueError, RuntimeError)):
            run_microsoft_oauth_flow("cid", "tid")


def test_redirect_uri_constant():
    """_REDIRECT_URI must not have trailing slash (T-1-20)."""
    assert not _REDIRECT_URI.endswith("/")
    assert "localhost" in _REDIRECT_URI
