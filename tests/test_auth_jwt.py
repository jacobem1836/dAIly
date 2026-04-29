"""Phase 18 INFRA-02: auth settings + model presence."""
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
