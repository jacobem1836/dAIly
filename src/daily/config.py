"""Application settings loaded from environment variables."""
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Required vars that have NO safe default — the app cannot operate without them.
# Mapped as field_name -> UPPER_SNAKE env var name for error messages.
_REQUIRED_VARS: dict[str, str] = {
    "vault_key": "VAULT_KEY",
    "jwt_secret": "JWT_SECRET",
    "openai_api_key": "OPENAI_API_KEY",
    "deepgram_api_key": "DEEPGRAM_API_KEY",
    "cartesia_api_key": "CARTESIA_API_KEY",
    "resend_api_key": "RESEND_API_KEY",
    "livekit_api_key": "LIVEKIT_API_KEY",
    "livekit_api_secret": "LIVEKIT_API_SECRET",
}

# LiveKit's public quickstart credentials (documented in their OSS README/
# livekit.yaml examples). Anyone can mint a valid room-join token offline
# with these — they must never be used outside a throwaway local dev
# container. Reject them outright at startup rather than trusting env
# presence alone.
_BAD_LIVEKIT_API_KEYS = {"devkey"}
_BAD_LIVEKIT_API_SECRETS = {"secret", "devsecret12345678901234567890123"}

# Well-known placeholder/weak values that must never be used as a real JWT
# signing secret, even if they happen to be >= 32 characters.
_WEAK_JWT_SECRETS = {
    "changeme",
    "change_me",
    "change-me",
    "secret",
    "password",
    "your-secret-key",
    "your_secret_key",
    "supersecret",
    "super-secret",
    "super_secret_key",
    "test",
    "testsecret",
    "jwtsecret",
    "jwt_secret",
    "jwt-secret",
    "12345678901234567890123456789012",
}
_MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://daily:daily_dev@localhost:5432/daily"
    database_url_psycopg: str = "postgresql://daily:daily_dev@localhost:5432/daily"
    vault_key: str = ""

    google_client_id: str = ""
    google_client_secret: str = ""

    slack_client_id: str = ""
    slack_client_secret: str = ""

    microsoft_client_id: str = ""
    microsoft_tenant_id: str = ""
    microsoft_client_secret: str = ""

    redis_url: str = "redis://localhost:6379/0"
    openai_api_key: str = ""
    deepgram_api_key: str = ""
    cartesia_api_key: str = ""

    # LiveKit (Phase 18 / D-05, D-08, D-09)
    # IMPORTANT: livekit_url must be a wss:// address reachable from mobile
    # devices — NOT ws://localhost:7880. iOS clients and the agent worker must
    # both point at the same server. Use your LiveKit Cloud URL or a publicly
    # accessible tunnel (e.g. wss://your-project.livekit.cloud).
    livekit_url: str = "ws://localhost:7880"
    # No safe default — these are validated as required, non-quickstart
    # values below (T-security: public LiveKit devkey/devsecret rejection).
    livekit_api_key: str = ""
    livekit_api_secret: str = ""

    briefing_email_top_n: int = 5  # per D-05
    briefing_schedule_time: str = "05:00"  # per D-13, default precompute time

    # App JWT auth (Phase 18 / D-01..D-04)
    jwt_secret: str = ""
    jwt_access_ttl_minutes: int = 15
    jwt_refresh_ttl_days: int = 90

    # Magic-link email delivery via Resend (Phase 19 / D-02)
    resend_api_key: str = ""
    resend_from_email: str = "dAIly <noreply@example.com>"
    magic_link_base_url: str = "https://app.example.com"

    # Universal Links (Phase 19 / D-03)
    apple_team_id: str = ""
    apple_bundle_id: str = "com.daily.ios"

    # Android App Links (Phase 20 / MOB-02)
    android_package_name: str = "com.daily.android"
    android_sha256_fingerprint: str = ""

    # Logging — runtime log level (read by logging setup at startup)
    log_level: str = "INFO"

    @model_validator(mode="after")
    def _require_critical_vars(self) -> "Settings":
        """Fail fast at startup if any required, no-safe-default vars are unset.

        Collects ALL missing required vars and raises a single error that names
        them all — so a developer sees everything missing in one message rather
        than fixing one var and hitting another error on the next boot.
        """
        missing = [
            env_name
            for field_name, env_name in _REQUIRED_VARS.items()
            if not getattr(self, field_name, "")
        ]
        if missing:
            var_list = ", ".join(missing)
            raise ValueError(
                f"Missing required environment variables: {var_list}. "
                "Copy .env.example to .env and fill them in."
            )

        # Additional strength/legitimacy checks — run only once all required
        # vars are confirmed present, so these messages are unambiguous.
        errors: list[str] = []

        if len(self.jwt_secret) < _MIN_JWT_SECRET_LENGTH:
            errors.append(
                f"JWT_SECRET must be at least {_MIN_JWT_SECRET_LENGTH} characters "
                f"(got {len(self.jwt_secret)}). Generate one with "
                "`openssl rand -hex 32`."
            )
        elif self.jwt_secret.lower() in _WEAK_JWT_SECRETS:
            errors.append(
                "JWT_SECRET is a well-known placeholder/weak value. Generate a "
                "real random secret with `openssl rand -hex 32`."
            )

        if self.livekit_api_key in _BAD_LIVEKIT_API_KEYS:
            errors.append(
                "LIVEKIT_API_KEY is set to LiveKit's public quickstart devkey. "
                "This is publicly known and lets anyone mint a valid room-join "
                "token — set a real, non-public LIVEKIT_API_KEY."
            )
        if self.livekit_api_secret in _BAD_LIVEKIT_API_SECRETS:
            errors.append(
                "LIVEKIT_API_SECRET is set to a known public/quickstart value. "
                "This is publicly known and lets anyone mint a valid room-join "
                "token — set a real, non-public LIVEKIT_API_SECRET."
            )

        if errors:
            raise ValueError(" ".join(errors))

        return self
