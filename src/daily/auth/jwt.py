"""App-layer JWT encode/decode (Phase 18, D-01).

HS256 access tokens carry `sub` (user_id) and `type=access` claims.
Refresh tokens are opaque (not JWTs) — see pairing.py.
"""
from datetime import datetime, timedelta, timezone

import jwt

from daily.config import Settings


def encode_access_token(user_id: int, settings: Settings) -> str:
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not configured")
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc)
        + timedelta(minutes=settings.jwt_access_ttl_minutes),
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str, settings: Settings) -> dict:
    """Decode + verify. Raises jwt.ExpiredSignatureError or jwt.InvalidTokenError."""
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
