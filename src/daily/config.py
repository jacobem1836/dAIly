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
    briefing_email_top_n: int = 5  # per D-05
    briefing_schedule_time: str = "05:00"  # per D-13, default precompute time
