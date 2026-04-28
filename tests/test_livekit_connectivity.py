"""Smoke tests for LiveKit infrastructure (Phase 18, INFRA-01)."""
import httpx
import pytest
from livekit.api import AccessToken, VideoGrants


def test_livekit_dev_container_reachable():
    """LiveKit dev container responds on localhost:7880. Skips if not running."""
    try:
        resp = httpx.get("http://localhost:7880", timeout=2.0)
    except (httpx.ConnectError, httpx.ConnectTimeout):
        pytest.skip("LiveKit dev container not running (docker compose up)")
    # LiveKit returns 404 on root HTTP GET — confirms the server is responding
    assert resp.status_code in (200, 404), f"Unexpected status {resp.status_code}"


def test_livekit_access_token_signs():
    """livekit-api SDK can mint a JWT with the dev key/secret."""
    token = (
        AccessToken("devkey", "secret")
        .with_identity("test-user")
        .with_grants(VideoGrants(room_join=True, room="test-room"))
        .to_jwt()
    )
    assert isinstance(token, str)
    assert len(token) > 50  # JWTs are long
    assert token.count(".") == 2  # JWT format: header.payload.signature
