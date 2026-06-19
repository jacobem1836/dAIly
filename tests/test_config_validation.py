"""Tests for Settings fail-fast startup validation.

These tests verify that:
- Settings construction raises a clear, aggregated error when required vars
  are empty/absent, naming ALL missing vars in a single message.
- Settings construction succeeds when required vars are present.
- Optional/defaulted vars (database_url, redis_url, livekit_*) absent does
  NOT raise — their dev defaults stand.
"""
import pytest
from pydantic import ValidationError

from daily.config import Settings

# Values used for a fully-valid Settings instance in tests.
# _env_file=None prevents tests from reading the project's real .env file,
# ensuring test isolation regardless of what the developer has locally.
_VALID_REQUIRED = {
    "_env_file": None,
    "vault_key": "dGVzdGtleS10ZXN0a2V5LXRlc3Rr",  # fake base64, not a real key
    "jwt_secret": "x" * 32,
    "openai_api_key": "sk-test-openai",
    "deepgram_api_key": "dg-test-key",
    "cartesia_api_key": "sk_car_test",
    "resend_api_key": "re_test_key",
}


class TestSettingsRequiredVarsPresent:
    """Settings must construct without error when all required vars are set."""

    def test_settings_constructs_with_required_vars(self):
        """Settings construction succeeds when all required vars are non-empty."""
        settings = Settings(**_VALID_REQUIRED)
        assert settings.vault_key == _VALID_REQUIRED["vault_key"]
        assert settings.jwt_secret == _VALID_REQUIRED["jwt_secret"]
        assert settings.openai_api_key == _VALID_REQUIRED["openai_api_key"]

    def test_optional_vars_use_dev_defaults(self):
        """database_url, redis_url, livekit_* use safe defaults — never raise."""
        settings = Settings(**_VALID_REQUIRED)
        assert "localhost" in settings.database_url or "localhost" in settings.redis_url
        assert settings.livekit_api_key == "devkey"
        assert settings.livekit_api_secret == "secret"


class TestSettingsRequiredVarsMissing:
    """Settings must raise a clear, aggregated error when required vars are absent."""

    def test_all_required_empty_raises_with_all_names(self):
        """All required vars empty raises one error listing ALL missing vars at once."""
        with pytest.raises((ValueError, ValidationError)) as exc_info:
            Settings(
                _env_file=None,
                vault_key="",
                jwt_secret="",
                openai_api_key="",
                deepgram_api_key="",
                cartesia_api_key="",
                resend_api_key="",
            )
        error_text = str(exc_info.value)
        # Must name at least two missing vars in the SAME message
        assert "VAULT_KEY" in error_text
        assert "JWT_SECRET" in error_text

    def test_error_message_mentions_env_example(self):
        """Error message should point at .env.example to guide the user."""
        with pytest.raises((ValueError, ValidationError)) as exc_info:
            Settings(_env_file=None, vault_key="", jwt_secret="", openai_api_key="")
        error_text = str(exc_info.value)
        assert ".env.example" in error_text

    def test_single_missing_var_raises(self):
        """Missing a single required var also raises."""
        partial = {k: v for k, v in _VALID_REQUIRED.items() if k != "vault_key"}
        with pytest.raises((ValueError, ValidationError)) as exc_info:
            Settings(**partial, vault_key="")
        assert "VAULT_KEY" in str(exc_info.value)

    def test_error_lists_all_six_required_vars_when_all_empty(self):
        """When all six required vars are empty, all six must appear in the error."""
        with pytest.raises((ValueError, ValidationError)) as exc_info:
            Settings(
                _env_file=None,
                vault_key="",
                jwt_secret="",
                openai_api_key="",
                deepgram_api_key="",
                cartesia_api_key="",
                resend_api_key="",
            )
        error_text = str(exc_info.value)
        required_env_names = [
            "VAULT_KEY",
            "JWT_SECRET",
            "OPENAI_API_KEY",
            "DEEPGRAM_API_KEY",
            "CARTESIA_API_KEY",
            "RESEND_API_KEY",
        ]
        missing_from_error = [name for name in required_env_names if name not in error_text]
        assert missing_from_error == [], (
            f"Error message missing these required var names: {missing_from_error}\n"
            f"Full error: {error_text}"
        )


class TestSettingsOptionalVarsDoNotRaise:
    """DB, Redis, LiveKit vars have safe defaults — their absence must not raise."""

    def test_integration_oauth_creds_can_be_empty(self):
        """OAuth creds (Google, Slack, Microsoft) are optional — empty is fine."""
        settings = Settings(
            **_VALID_REQUIRED,
            google_client_id="",
            google_client_secret="",
            slack_client_id="",
            slack_client_secret="",
            microsoft_client_id="",
            microsoft_tenant_id="",
        )
        assert settings.google_client_id == ""  # noqa: SIM910 (intentional empty string check)


class TestSettingsLogLevel:
    """LOG_LEVEL should be available on Settings with INFO default."""

    def test_log_level_has_default(self):
        """log_level field exists and defaults to INFO."""
        settings = Settings(**_VALID_REQUIRED)
        assert settings.log_level.upper() == "INFO"

    def test_log_level_can_be_overridden(self):
        """log_level can be set to DEBUG."""
        settings = Settings(**_VALID_REQUIRED, log_level="DEBUG")
        assert settings.log_level.upper() == "DEBUG"
