"""Phase 18 INFRA-02: LiveKit token unit tests (room name, TTL, identity)."""
import re
import time
import jwt as pyjwt
import pytest

from daily.config import Settings
from daily.livekit.tokens import create_livekit_token, LIVEKIT_TOKEN_TTL


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("LIVEKIT_API_KEY", "test-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "test-secret-32-bytes-padded-x")
    monkeypatch.setenv("LIVEKIT_URL", "ws://localhost:7880")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    return Settings()


def test_room_name_format(settings):
    token, room = create_livekit_token(42, settings)
    assert re.match(r"^session-42-\d+$", room), f"room {room} does not match format"


def test_token_decodes_with_secret(settings):
    token, room = create_livekit_token(42, settings)
    # LiveKit JWT is HS256 signed with api_secret
    payload = pyjwt.decode(
        token,
        settings.livekit_api_secret,
        algorithms=["HS256"],
        options={"verify_aud": False},
    )
    assert payload["sub"] == "42"
    # TTL ~ 1 hour — LiveKit uses nbf (not before) instead of iat
    ttl = payload["exp"] - payload["nbf"]
    assert abs(ttl - int(LIVEKIT_TOKEN_TTL.total_seconds())) <= 5


def test_room_name_unique_across_seconds(settings):
    _, r1 = create_livekit_token(7, settings)
    time.sleep(1.1)
    _, r2 = create_livekit_token(7, settings)
    assert r1 != r2


def test_room_name_uses_session_prefix(settings):
    _, room = create_livekit_token(99, settings)
    assert room.startswith("session-")
