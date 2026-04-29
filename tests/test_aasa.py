"""Tests for GET /.well-known/apple-app-site-association (Phase 19, Task 3).

Verifies the AASA endpoint returns valid JSON with the correct Team ID and
bundle ID, no redirects, and the correct content-type header.
"""
import pytest
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("VAULT_KEY", "y" * 32)
    monkeypatch.setenv("APPLE_TEAM_ID", "ABCD1234")
    monkeypatch.setenv("APPLE_BUNDLE_ID", "com.test.daily")


@pytest.fixture
async def client():
    from daily.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Test 1: Returns 200 with application/json content-type
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_aasa_returns_200_json(client):
    """GET /.well-known/apple-app-site-association returns 200 with application/json."""
    r = await client.get("/.well-known/apple-app-site-association")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")


# ---------------------------------------------------------------------------
# Test 2: Response is not redirected (no 301/302)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_aasa_no_redirect(client):
    """AASA endpoint does not redirect (Apple CDN rejects redirects)."""
    # httpx follows redirects by default; check the final status is still 200
    # and that no redirect occurred (status_code is 200, not 3xx)
    r = await client.get(
        "/.well-known/apple-app-site-association",
        follow_redirects=False,
    )
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Test 3: Body matches AASA schema with correct appID and /pair path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_aasa_body_schema(client):
    """AASA body has appID = TEAM_ID.BUNDLE_ID and paths includes /pair."""
    r = await client.get("/.well-known/apple-app-site-association")
    body = r.json()

    assert "applinks" in body
    applinks = body["applinks"]
    assert "apps" in applinks
    assert "details" in applinks

    details = applinks["details"]
    assert len(details) >= 1

    detail = details[0]
    assert detail["appID"] == "ABCD1234.com.test.daily"
    assert "/pair" in detail["paths"]
