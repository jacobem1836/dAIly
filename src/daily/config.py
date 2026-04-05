"""Application settings loaded from environment variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str = "postgresql+asyncpg://daily:daily_dev@localhost:5432/daily"
    vault_key: str = ""

    google_client_id: str = ""
    google_client_secret: str = ""

    slack_client_id: str = ""
    slack_client_secret: str = ""

    microsoft_client_id: str = ""
    microsoft_tenant_id: str = ""
