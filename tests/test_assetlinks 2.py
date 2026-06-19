"""Tests for GET /.well-known/assetlinks.json (Phase 20, Plan 01 / MOB-02).

Verifies the Android App Links assetlinks.json endpoint returns a valid JSON
array with the correct structure, package name, and SHA-256 fingerprints.
No redirects; direct application/json response required.
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
    monkeypatch.setenv("ANDROID_PACKAGE_NAME", "com.test.daily.android")
    monkeypatch.setenv("ANDROID_SHA256_FINGERPRINT", "AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99")


@pytest.fixture
async def client():
    from daily.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Test 1: GET /.well-known/assetlinks.json returns 200
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_assetlinks_returns_200(client):
    """GET /.well-known/assetlinks.json returns HTTP 200."""
    r = await client.get("/.well-known/assetlinks.json")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Test 2: Response Content-Type is application/json
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_assetlinks_content_type(client):
    """assetlinks.json endpoint returns Content-Type: application/json."""
    r = await client.get("/.well-known/assetlinks.json")
    assert r.headers["content-type"].startswith("application/json")


# ---------------------------------------------------------------------------
# Test 3: Response body is a JSON ARRAY (not object) with one element
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_assetlinks_is_array(client):
    """assetlinks.json response body is a JSON array with exactly one element."""
    r = await client.get("/.well-known/assetlinks.json")
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 1


# ---------------------------------------------------------------------------
# Test 4: Element has key "relation" == ["delegate_permission/common.handle_all_urls"]
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_assetlinks_relation(client):
    """assetlinks.json element has correct relation value."""
    r = await client.get("/.well-known/assetlinks.json")
    element = r.json()[0]
    assert "relation" in element
    assert element["relation"] == ["delegate_permission/common.handle_all_urls"]


# ---------------------------------------------------------------------------
# Test 5: element.target.namespace == "android_app"
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_assetlinks_namespace(client):
    """assetlinks.json target.namespace is 'android_app'."""
    r = await client.get("/.well-known/assetlinks.json")
    target = r.json()[0]["target"]
    assert target["namespace"] == "android_app"


# ---------------------------------------------------------------------------
# Test 6: element.target.package_name matches ANDROID_PACKAGE_NAME env var
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_assetlinks_package_name(client):
    """assetlinks.json target.package_name reflects Settings.android_package_name."""
    r = await client.get("/.well-known/assetlinks.json")
    target = r.json()[0]["target"]
    assert target["package_name"] == "com.test.daily.android"


# ---------------------------------------------------------------------------
# Test 7: Single fingerprint → sha256_cert_fingerprints is a list of one
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_assetlinks_single_fingerprint(client):
    """Single fingerprint in env → sha256_cert_fingerprints is a one-element list."""
    r = await client.get("/.well-known/assetlinks.json")
    target = r.json()[0]["target"]
    assert "sha256_cert_fingerprints" in target
    fingerprints = target["sha256_cert_fingerprints"]
    assert isinstance(fingerprints, list)
    assert len(fingerprints) == 1
    assert fingerprints[0] == "AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99"


# ---------------------------------------------------------------------------
# Test 8: Comma-separated fingerprints split into multiple list elements
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_assetlinks_multi_fingerprint(monkeypatch):
    """Comma-separated ANDROID_SHA256_FINGERPRINT produces multiple list entries."""
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("VAULT_KEY", "y" * 32)
    monkeypatch.setenv("ANDROID_PACKAGE_NAME", "com.test.daily.android")
    monkeypatch.setenv("ANDROID_SHA256_FINGERPRINT", "AA:BB,CC:DD")

    from daily.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/.well-known/assetlinks.json")

    target = r.json()[0]["target"]
    fingerprints = target["sha256_cert_fingerprints"]
    assert isinstance(fingerprints, list)
    assert len(fingerprints) == 2
    assert fingerprints[0] == "AA:BB"
    assert fingerprints[1] == "CC:DD"
