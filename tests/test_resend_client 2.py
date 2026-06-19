"""Tests for the Resend email client (Phase 19, Task 1).

Uses monkeypatch + a fake httpx.AsyncClient to avoid real HTTP calls.
"""
import pytest

from daily.config import Settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_settings(**overrides) -> Settings:
    base = {
        "JWT_SECRET": "x" * 32,
        "VAULT_KEY": "y" * 32,
        "RESEND_API_KEY": "test-api-key",
        "RESEND_FROM_EMAIL": "dAIly <noreply@example.com>",
        "MAGIC_LINK_BASE_URL": "https://app.example.com",
        "APPLE_TEAM_ID": "ABCD1234",
        "APPLE_BUNDLE_ID": "com.daily.ios",
    }
    import os
    for k, v in {**base, **overrides}.items():
        os.environ[k] = v
    return Settings()


# ---------------------------------------------------------------------------
# Test 1: POST to api.resend.com with correct Authorization header
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_magic_link_posts_to_resend_with_auth(monkeypatch):
    """send_magic_link issues POST to api.resend.com with Bearer auth header."""
    captured = {}

    class FakeResponse:
        status_code = 200
        text = "ok"

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, *, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    import daily.email.resend_client as rc
    monkeypatch.setattr(rc.httpx, "AsyncClient", lambda: FakeAsyncClient())

    settings = _make_settings()
    await rc.send_magic_link("user@example.com", "123456", settings=settings)

    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["headers"]["Authorization"] == "Bearer test-api-key"


# ---------------------------------------------------------------------------
# Test 2: Email body contains the magic link URL
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_magic_link_body_contains_pair_url(monkeypatch):
    """Email HTML body contains the correct magic link URL."""
    captured = {}

    class FakeResponse:
        status_code = 200
        text = "ok"

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, *, headers, json):
            captured["json"] = json
            return FakeResponse()

    import daily.email.resend_client as rc
    monkeypatch.setattr(rc.httpx, "AsyncClient", lambda: FakeAsyncClient())

    settings = _make_settings()
    await rc.send_magic_link("user@example.com", "123456", settings=settings)

    html = captured["json"]["html"]
    assert "https://app.example.com/pair?code=123456" in html


# ---------------------------------------------------------------------------
# Test 3: Non-200 response raises ResendError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_magic_link_raises_on_non_200(monkeypatch):
    """Non-200 Resend response raises ResendError."""

    class FakeResponse:
        status_code = 422
        text = "Unprocessable Entity"

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, *, headers, json):
            return FakeResponse()

    import daily.email.resend_client as rc
    monkeypatch.setattr(rc.httpx, "AsyncClient", lambda: FakeAsyncClient())

    settings = _make_settings()
    with pytest.raises(rc.ResendError):
        await rc.send_magic_link("user@example.com", "000000", settings=settings)


# ---------------------------------------------------------------------------
# Test 4: Settings exposes all required env vars
# ---------------------------------------------------------------------------

def test_settings_exposes_resend_and_apple_fields(monkeypatch):
    """Settings exposes resend_api_key, resend_from_email, magic_link_base_url, apple_team_id, apple_bundle_id."""
    settings = _make_settings()
    assert settings.resend_api_key == "test-api-key"
    assert settings.resend_from_email == "dAIly <noreply@example.com>"
    assert settings.magic_link_base_url == "https://app.example.com"
    assert settings.apple_team_id == "ABCD1234"
    assert settings.apple_bundle_id == "com.daily.ios"


# ---------------------------------------------------------------------------
# Test 5: Email body contains plain-text OTP code for manual entry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_magic_link_body_contains_code_fallback(monkeypatch):
    """Email HTML body contains the plain-text OTP code for manual entry."""
    captured = {}

    class FakeResponse:
        status_code = 200
        text = "ok"

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, *, headers, json):
            captured["json"] = json
            return FakeResponse()

    import daily.email.resend_client as rc
    monkeypatch.setattr(rc.httpx, "AsyncClient", lambda: FakeAsyncClient())

    settings = _make_settings()
    await rc.send_magic_link("user@example.com", "654321", settings=settings)

    html = captured["json"]["html"]
    assert "Or enter code manually: 654321" in html
