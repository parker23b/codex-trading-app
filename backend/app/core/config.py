from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Algo Trading Platform API"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/trading_platform"
    broker_mode: str = "DEMO"
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    @field_validator("broker_mode")
    @classmethod
    def validate_broker_mode(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEMO", "LIVE"}:
            raise ValueError("BROKER_MODE must be DEMO or LIVE.")
        return normalized


@lru_cache
def get_settings() -> Settings:
    return Settings()

