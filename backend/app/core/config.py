from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Algo Trading Platform API"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    database_url: str = "sqlite:///./trading_platform.db"
    broker_provider: str = "IG"
    broker_mode: str = "DEMO"
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    simulation_mode: bool = True
    simulation_seed: int = 20260320
    starting_account_value: float = 100_000.0
    dashboard_recent_trade_window: int = 30
    market_data_poll_interval_seconds: float = 2.0
    ig_api_key: str | None = None
    ig_username: str | None = None
    ig_password: str | None = None
    ig_account_id: str | None = None
    ig_api_base_url: str | None = None
    ig_request_timeout_seconds: float = 10.0
    ig_trading_enabled: bool = False
    ig_market_cache_ttl_seconds: float = 30.0
    ig_market_cache_stale_ttl_seconds: float = 300.0
    ig_verify_ssl: bool = True
    ig_ca_bundle_path: str | None = None

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("broker_mode")
    @classmethod
    def validate_broker_mode(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEMO", "LIVE"}:
            raise ValueError("BROKER_MODE must be DEMO or LIVE.")
        return normalized

    @field_validator("broker_provider")
    @classmethod
    def validate_broker_provider(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"IG"}:
            raise ValueError("BROKER_PROVIDER must currently be IG.")
        return normalized

    @field_validator("market_data_poll_interval_seconds")
    @classmethod
    def validate_market_data_poll_interval_seconds(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("MARKET_DATA_POLL_INTERVAL_SECONDS must be greater than 0.")
        return value

    @field_validator("ig_market_cache_ttl_seconds", "ig_market_cache_stale_ttl_seconds")
    @classmethod
    def validate_positive_ig_market_cache_ttls(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("IG market cache TTL settings must be greater than 0.")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
