from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+psycopg://ipodekho:ipodekho@localhost:5432/ipodekho"
    cors_origins: str = "http://localhost:3000"
    raw_snapshot_bucket: str | None = None
    r2_bucket: str | None = None
    r2_endpoint_url: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    rhp_allowed_hosts: str = "nseindia.com,bseindia.com"
    rhp_download_max_bytes: int = 200 * 1024 * 1024
    rhp_download_connect_timeout_seconds: float = 10
    rhp_download_read_timeout_seconds: float = 60
    rhp_max_redirects: int = 5
    rhp_archive_batch_size: int = 10
    gemini_safe_pdf_bytes: int = 45 * 1024 * 1024
    gemini_max_pdf_pages: int = 1000
    rhp_chunk_max_bytes: int = 40 * 1024 * 1024
    rhp_chunk_max_pages: int = 300
    gemini_api_key: str | None = None
    rhp_primary_model: str = "gemini-3.5-flash-lite"
    rhp_prompt_version: str = "rhp-v1.8"
    rhp_schema_version: str = "rhp-v1.1"
    rhp_extraction_batch_size: int = 5
    rhp_extraction_max_attempts: int = 3
    rhp_auto_approve: bool = True
    gemini_file_timeout_seconds: int = 300
    gemini_file_poll_seconds: float = 2
    gemini_request_timeout_seconds: int = 180
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

    @property
    def rhp_allowed_host_list(self) -> list[str]:
        return [item.strip().lower() for item in self.rhp_allowed_hosts.split(",") if item.strip()]

    @property
    def r2_configured(self) -> bool:
        return all(
            (
                self.r2_bucket,
                self.r2_endpoint_url,
                self.r2_access_key_id,
                self.r2_secret_access_key,
            )
        )

    @property
    def r2_configuration_requested(self) -> bool:
        return any(
            (
                self.r2_bucket,
                self.r2_endpoint_url,
                self.r2_access_key_id,
                self.r2_secret_access_key,
            )
        )

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key and self.gemini_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
