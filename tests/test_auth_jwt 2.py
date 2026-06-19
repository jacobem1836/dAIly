"""Phase 18 INFRA-02: auth settings + model presence + JWT round-trip."""
import os
import pytest
from daily.config import Settings
from daily.db.models import PairingCode, DeviceToken


def test_settings_have_jwt_fields(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    s = Settings()
    assert s.jwt_secret == "x" * 32
    assert s.jwt_access_ttl_minutes == 15
    assert s.jwt_refresh_ttl_days == 90


def test_pairing_code_model_columns():
    cols = {c.name for c in PairingCode.__table__.columns}
    assert {"id", "user_id", "code", "used", "expires_at", "created_at"} <= cols


def test_device_token_model_columns():
    cols = {c.name for c in DeviceToken.__table__.columns}
    assert {
        "id", "user_id", "device_name", "encrypted_refresh_token",
        "expires_at", "revoked", "created_at", "last_used_at",
    } <= cols


import jwt as pyjwt
from datetime import datetime, timedelta, timezone
from daily.auth.jwt import encode_access_token, decode_access_token
from daily.auth.pairing import generate_pairing_code, generate_refresh_token


def _settings(monkeypatch, secret="a" * 32):
    monkeypatch.setenv("JWT_SECRET", secret)
    return Settings()


def test_jwt_round_trip(monkeypatch):
    s = _settings(monkeypatch)
    token = encode_access_token(42, s)
    payload = decode_access_token(token, s)
    assert payload["sub"] == "42"
    assert payload["type"] == "access"


def test_jwt_expired_rejected(monkeypatch):
    s = _settings(monkeypatch)
    # Hand-craft an expired token
    expired = pyjwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(seconds=1), "type": "access"},
        s.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(pyjwt.ExpiredSignatureError):
        decode_access_token(expired, s)


def test_jwt_wrong_secret_rejected(monkeypatch):
    s1 = _settings(monkeypatch, "a" * 32)
    token = encode_access_token(1, s1)
    s2 = _settings(monkeypatch, "b" * 32)
    with pytest.raises(pyjwt.InvalidTokenError):
        decode_access_token(token, s2)


def test_pairing_code_format():
    code = generate_pairing_code()
    assert code.isdigit()
    assert len(code) == 6
    assert 100000 <= int(code) <= 999999


def test_refresh_token_format():
    tok = generate_refresh_token()
    assert isinstance(tok, str)
    assert len(tok) >= 40  # token_urlsafe(32) → 43 chars
