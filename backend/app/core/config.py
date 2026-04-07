from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


BACKEND_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


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
    starting_account_value: float = 100_000.0
    dashboard_recent_trade_window: int = 30
    market_data_poll_interval_seconds: float = 2.0
    runtime_max_open_positions: int = 6
    runtime_max_positions_per_strategy: int = 3
    runtime_max_open_risk_percent: float = 4.0
    runtime_daily_loss_limit: float = 2_000.0
    runtime_one_position_per_instrument: bool = False
    runtime_max_position_notional: float = 25_000.0
    runtime_max_spread_percent_of_price: float = 0.0015
    runtime_price_stale_after_seconds: float = 15.0
    runtime_entry_burst_limit: int = 3
    runtime_entry_burst_window_seconds: int = 300
    runtime_failed_entry_retry_cooldown_seconds: int = 120
    runtime_cooldown_after_loss_seconds: int = 20
    runtime_cooldown_after_exit_seconds: int = 10
    runtime_duplicate_signal_window_seconds: int = 30
    runtime_max_unhealthy_runtimes: int = 0
    runtime_global_entry_kill_switch: bool = False
    ai_reviewer_llm_enabled: bool = False
    ai_reviewer_llm_provider: str = "disabled"
    ai_reviewer_llm_model: str = "unconfigured"
    ig_api_key: str | None = None
    ig_username: str | None = None
    ig_password: str | None = None
    ig_account_id: str | None = None
    ig_api_base_url: str | None = None
    ig_request_timeout_seconds: float = 10.0
    ig_trading_enabled: bool = False
    ig_streaming_enabled: bool = True
    ig_streaming_watch_interval_seconds: float = 1.0
    ig_market_cache_ttl_seconds: float = 30.0
    ig_market_cache_stale_ttl_seconds: float = 300.0
    ig_verify_ssl: bool = True
    ig_ca_bundle_path: str | None = None

    model_config = SettingsConfigDict(env_file=BACKEND_ENV_FILE, case_sensitive=False, extra="ignore")

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

    @field_validator("market_data_poll_interval_seconds", "ig_streaming_watch_interval_seconds")
    @classmethod
    def validate_positive_poll_intervals(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Polling interval settings must be greater than 0.")
        return value

    @field_validator(
        "runtime_max_open_positions",
        "runtime_max_positions_per_strategy",
        "runtime_entry_burst_limit",
        "runtime_entry_burst_window_seconds",
        "runtime_failed_entry_retry_cooldown_seconds",
        "runtime_cooldown_after_loss_seconds",
        "runtime_cooldown_after_exit_seconds",
        "runtime_duplicate_signal_window_seconds",
        mode="after",
    )
    @classmethod
    def validate_positive_runtime_position_limits(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Runtime position limit settings must be greater than 0.")
        return value

    @field_validator(
        "runtime_max_open_risk_percent",
        "runtime_daily_loss_limit",
        "runtime_max_position_notional",
        "runtime_max_spread_percent_of_price",
        "runtime_price_stale_after_seconds",
        mode="after",
    )
    @classmethod
    def validate_positive_runtime_numeric_limits(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Runtime numeric limit settings must be greater than 0.")
        return value

    @field_validator("runtime_max_unhealthy_runtimes", mode="after")
    @classmethod
    def validate_non_negative_runtime_health_limit(cls, value: int) -> int:
        if value < 0:
            raise ValueError("RUNTIME_MAX_UNHEALTHY_RUNTIMES must be zero or greater.")
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
