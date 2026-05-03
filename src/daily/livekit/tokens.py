"""LiveKit AccessToken wrapper (Phase 18, INFRA-02 / D-08, D-09)."""
from datetime import datetime, timedelta, timezone

from livekit.api import AccessToken, VideoGrants

from daily.config import Settings


LIVEKIT_TOKEN_TTL = timedelta(hours=1)  # per D-09


def create_livekit_token(user_id: int, settings: Settings) -> tuple[str, str]:
    """
    Mint a LiveKit JWT scoped to an ephemeral room for `user_id`.

    Returns (jwt_token, room_name). Room is `session-{user_id}-{unix_timestamp}` per D-08.
    A fresh AccessToken is constructed per call (RESEARCH.md Pitfall 6 — not thread-safe to reuse).
    """
    timestamp = int(datetime.now(timezone.utc).timestamp())
    room_name = f"session-{user_id}-{timestamp}"

    token = (
        AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(str(user_id))
        .with_name(f"user-{user_id}")
        .with_ttl(LIVEKIT_TOKEN_TTL)
        .with_grants(VideoGrants(room_join=True, room=room_name))
        .to_jwt()
    )
    return token, room_name
