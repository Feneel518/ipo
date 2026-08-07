from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "IPO Dekho Worker"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000
    database_url: SecretStr | None = None
    scheduler_enabled: bool = True
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None
    watchdog_digest_hour: int = Field(default=9, ge=0, le=23)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
