"""Schema privacy constraint tests — SEC-04/D-06 enforcement."""
import pytest
from daily.db.models import User, IntegrationToken


FORBIDDEN_COLUMN_PATTERNS = {"body", "raw_body", "content", "message_body"}


def _column_names(model) -> set[str]:
    return {col.name for col in model.__table__.columns}


def test_user_has_tablename():
    assert hasattr(User, "__tablename__")
    assert User.__tablename__ == "users"


def test_integration_token_has_tablename():
    assert hasattr(IntegrationToken, "__tablename__")
    assert IntegrationToken.__tablename__ == "integration_tokens"


def test_integration_token_required_fields():
    cols = _column_names(IntegrationToken)
    required = {
        "id",
        "user_id",
        "provider",
        "encrypted_access_token",
        "encrypted_refresh_token",
        "token_expiry",
        "scopes",
        "created_at",
        "updated_at",
    }
    for field in required:
        assert field in cols, f"IntegrationToken missing required column: {field}"


def test_user_no_forbidden_columns():
    cols = _column_names(User)
    for forbidden in FORBIDDEN_COLUMN_PATTERNS:
        assert forbidden not in cols, f"User has forbidden column: {forbidden}"


def test_integration_token_no_forbidden_columns():
    cols = _column_names(IntegrationToken)
    for forbidden in FORBIDDEN_COLUMN_PATTERNS:
        assert forbidden not in cols, f"IntegrationToken has forbidden column: {forbidden}"


def test_integration_token_has_encrypted_columns():
    cols = _column_names(IntegrationToken)
    assert "encrypted_access_token" in cols
    assert "encrypted_refresh_token" in cols
