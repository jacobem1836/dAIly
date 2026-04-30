"""Application settings loaded from environment variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    redis_url: str = "redis://localhost:6379/0"
    openai_api_key: str = ""
    deepgram_api_key: str = ""
    cartesia_api_key: str = ""

    # LiveKit (Phase 18 / D-05, D-08, D-09)
    livekit_url: str = "ws://localhost:7880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "secret"

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
    android_sha256_fingerprint: str = ""  # colon-separated hex; comma-separated list when multiple
