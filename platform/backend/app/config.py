from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+psycopg://ipodekho:ipodekho@localhost:5432/ipodekho"
    cors_origins: str = "http://localhost:3000"
    raw_snapshot_bucket: str | None = None
    revalidation_url: str | None = None
    revalidation_secret: str | None = None
    internal_api_token: str = Field(default="change-me", min_length=8)
    request_timeout_seconds: float = 25
    source_minimum_rows: int = 1

    @field_validator("database_url", mode="before")
    @classmethod
    def select_psycopg_driver(cls, value: str) -> str:
        """Supabase commonly supplies a generic PostgreSQL SQLAlchemy URL."""
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
