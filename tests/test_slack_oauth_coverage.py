"""Coverage uplift for slack/auth.py — tests run_slack_oauth_flow via mocks.

Covers lines 67-130 (run_slack_oauth_flow) by mocking browser/server/httpx.
RuntimeError path + success path via callback invocation brings coverage to 80%+.
"""
import asyncio
import pytest
from unittest.mock import MagicMock, patch

from daily.integrations.slack.auth import (
    SLACK_BOT_SCOPES,
    SLACK_AUTHORIZE_URL,
    SLACK_TOKEN_URL,
    run_slack_oauth_flow,
)


# ---------------------------------------------------------------------------
# run_slack_oauth_flow — timeout / RuntimeError path
# ---------------------------------------------------------------------------


def test_run_slack_oauth_flow_timeout_raises():
    """run_slack_oauth_flow raises RuntimeError when no bot token received."""
    with patch("daily.integrations.slack.auth.webbrowser.open"), \
         patch("daily.integrations.slack.auth.uvicorn.Server") as mock_server_cls, \
         patch("daily.integrations.slack.auth.uvicorn.Config"):

        mock_server_cls.return_value.run.return_value = None  # no-op

        with pytest.raises(RuntimeError, match="no bot token received"):
            run_slack_oauth_flow("fake-client-id", "fake-client-secret")


def test_run_slack_oauth_flow_builds_auth_url():
    """run_slack_oauth_flow includes all bot scopes in authorize URL."""
    opened = []

    with patch("daily.integrations.slack.auth.webbrowser.open", side_effect=opened.append), \
         patch("daily.integrations.slack.auth.uvicorn.Server") as mock_server_cls, \
         patch("daily.integrations.slack.auth.uvicorn.Config"):

        mock_server_cls.return_value.run.return_value = None

        with pytest.raises(RuntimeError):
            run_slack_oauth_flow("cid", "csecret")

    assert len(opened) == 1
    from urllib.parse import unquote
    decoded = unquote(opened[0])
    for scope in SLACK_BOT_SCOPES:
        assert scope in decoded


def test_run_slack_oauth_flow_uses_slack_authorize_url():
    """run_slack_oauth_flow uses SLACK_AUTHORIZE_URL as base."""
    opened = []

    with patch("daily.integrations.slack.auth.webbrowser.open", side_effect=opened.append), \
         patch("daily.integrations.slack.auth.uvicorn.Server") as mock_server_cls, \
         patch("daily.integrations.slack.auth.uvicorn.Config"):

        mock_server_cls.return_value.run.return_value = None

        with pytest.raises(RuntimeError):
            run_slack_oauth_flow("cid", "csecret")

    assert opened[0].startswith(SLACK_AUTHORIZE_URL)


# ---------------------------------------------------------------------------
# run_slack_oauth_flow — success path via captured callback_app
# ---------------------------------------------------------------------------


def test_run_slack_oauth_flow_success():
    """run_slack_oauth_flow returns bot token on successful Slack exchange."""
    captured_apps = []

    def capture_config(app, **kwargs):
        captured_apps.append(app)
        return MagicMock()

    class FakeServer:
        def __init__(self, config):
            pass

        def run(self):
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

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"ok": True, "access_token": "xoxb-fake-bot-token"}

    with patch("daily.integrations.slack.auth.webbrowser.open"), \
         patch("daily.integrations.slack.auth.uvicorn.Config", side_effect=capture_config), \
         patch("daily.integrations.slack.auth.uvicorn.Server", FakeServer), \
         patch("daily.integrations.slack.auth.httpx.post", return_value=mock_response):

        result = run_slack_oauth_flow("fake-client-id", "fake-client-secret")

    assert result == "xoxb-fake-bot-token"


def test_run_slack_oauth_flow_slack_error_in_callback():
    """run_slack_oauth_flow callback handles Slack error response (ok=False)."""
    captured_apps = []

    def capture_config(app, **kwargs):
        captured_apps.append(app)
        return MagicMock()

    class FakeServer:
        def __init__(self, config):
            pass

        def run(self):
            import httpx
            from httpx import ASGITransport

            app = captured_apps[0]

            async def invoke():
                transport = ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
                    await c.get("/callback?code=bad_code")

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(invoke())
            finally:
                loop.close()

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"ok": False, "error": "invalid_code"}

    with patch("daily.integrations.slack.auth.webbrowser.open"), \
         patch("daily.integrations.slack.auth.uvicorn.Config", side_effect=capture_config), \
         patch("daily.integrations.slack.auth.uvicorn.Server", FakeServer), \
         patch("daily.integrations.slack.auth.httpx.post", return_value=mock_response):

        with pytest.raises(RuntimeError):
            run_slack_oauth_flow("fake-client-id", "fake-client-secret")
