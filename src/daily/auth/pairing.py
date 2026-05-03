"""Pairing code + refresh token generation (Phase 18, D-01..D-02)."""
import secrets
from datetime import datetime, timedelta, timezone

PAIRING_CODE_TTL_SECONDS = 300  # 5 minutes


def generate_pairing_code() -> str:
    """Cryptographically secure 6-digit numeric code (100000-999999)."""
    return str(secrets.randbelow(900000) + 100000)


def generate_refresh_token() -> str:
    """Opaque 43-char URL-safe refresh token (32 bytes of entropy)."""
    return secrets.token_urlsafe(32)


def code_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=PAIRING_CODE_TTL_SECONDS)
