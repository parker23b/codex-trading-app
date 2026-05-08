from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


BACKEND_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
BACKEND_ROOT = BACKEND_ENV_FILE.parent
DEFAULT_SQLITE_DB_PATH = BACKEND_ROOT / "trading_platform.db"


class Settings(BaseSettings):
    app_name: str = "Algo Trading Platform API"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    log_level: str = "INFO"
    database_url: str = f"sqlite:///{DEFAULT_SQLITE_DB_PATH.as_posix()}"
    broker_provider: str = "IG"
    broker_mode: str = "DEMO"
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    starting_account_value: float = 100_000.0
    dashboard_recent_trade_window: int = 30
    market_data_poll_interval_seconds: float = 2.0
    max_price_age_ms: float = 5_000.0
    max_spread_pips: float = 2.0
    market_status_cache_ttl_ms: float = 250.0
    system_health_heartbeat_interval_seconds: float = 5.0
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
    allocation_enabled: bool = True
    allocation_default_risk_per_trade_percent: float = 0.35
    allocation_fallback_stop_distance_percent: float = 0.005
    allocation_max_new_positions_per_cycle: int = 2
    allocation_max_new_risk_per_cycle_percent: float = 1.25
    allocation_max_risk_per_strategy_percent: float = 1.5
    allocation_max_risk_per_family_percent: float = 2.0
    allocation_max_risk_per_instrument_percent: float = 1.0
    allocation_max_risk_per_currency_percent: float = 2.0
    allocation_max_gross_exposure_percent: float = 150.0
    allocation_under_minimum_round_up_tolerance_percent: float = 10.0
    allocation_drift_warning_percent: float = 10.0
    allocation_drift_critical_percent: float = 25.0
    allocation_alert_window_minutes: int = 240
    allocation_alert_revalidation_failure_threshold: int = 2
    allocation_alert_broker_submission_failure_threshold: int = 2
    allocation_alert_under_minimum_rejection_threshold: int = 3
    allocation_alert_hard_risk_block_threshold: int = 3
    allocation_alert_concentration_warning_utilization_percent: float = 80.0
    autonomous_control_enabled: bool = True
    autonomous_candidate_instruments_per_family: int = 4
    trade_allocator_enabled: bool = True
    trade_allocator_signal_stale_after_seconds: float = 15.0
    trade_allocator_max_decisions_per_cycle: int = 2
    trade_allocator_max_open_positions_per_instrument: int = 1
    ai_reviewer_llm_enabled: bool = False
    ai_reviewer_llm_provider: str = "disabled"
    ai_reviewer_llm_model: str = "unconfigured"
    operator_api_token: str | None = None
    ig_api_key: str | None = None
    ig_username: str | None = None
    ig_password: str | None = None
    ig_account_id: str | None = None
    ig_api_base_url: str | None = None
    ig_request_timeout_seconds: float = 10.0
    ig_trading_enabled: bool = False
    ig_streaming_enabled: bool = True
    ig_streaming_watch_interval_seconds: float = 1.0
    ig_streaming_stale_after_seconds: float = 20.0
    ig_streaming_transition_debounce_seconds: float = 10.0
    ig_streaming_max_instruments: int = 8
    ig_streaming_max_promotions_per_minute: int = 4
    ig_streaming_requested_frequency: str = "2.0"
    ig_streaming_min_tier1_residency_seconds: int = 30
    ig_streaming_demotion_cooldown_seconds: int = 120
    ig_streaming_max_subscription_churn_per_minute: int = 8
    ig_streaming_promotion_score_threshold: float = 0.7
    ig_streaming_eviction_score_threshold: float = 0.5
    ig_streaming_asset_class_slot_budgets: Annotated[dict[str, int], NoDecode] = {}
    ig_streaming_seed_instruments: Annotated[list[str], NoDecode] = []
    tier2_refresh_enabled: bool = True
    tier2_refresh_interval_seconds: float = 30.0
    tier2_refresh_batch_size: int = 5
    tier2_refresh_stale_after_seconds: float = 120.0
    tier2_seed_instruments: Annotated[list[str], NoDecode] = []
    tier2_promotion_score_threshold: float = 0.75
    tier2_promotion_ttl_seconds: int = 300
    ig_market_cache_ttl_seconds: float = 30.0
    ig_market_cache_stale_ttl_seconds: float = 300.0
    ig_verify_ssl: bool = True
    ig_ca_bundle_path: str | None = None
    testing_routes_enabled: bool = True

    model_config = SettingsConfigDict(
        env_file=BACKEND_ENV_FILE, case_sensitive=False, extra="ignore"
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("ig_streaming_seed_instruments", mode="before")
    @classmethod
    def parse_seed_instruments(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [
                instrument.strip()
                for instrument in value.split(",")
                if instrument.strip()
            ]
        return value

    @field_validator("tier2_seed_instruments", mode="before")
    @classmethod
    def parse_tier2_seed_instruments(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [
                instrument.strip()
                for instrument in value.split(",")
                if instrument.strip()
            ]
        return value

    @field_validator("ig_streaming_asset_class_slot_budgets", mode="before")
    @classmethod
    def parse_ig_streaming_asset_class_slot_budgets(
        cls, value: str | dict[str, int]
    ) -> dict[str, int]:
        if isinstance(value, dict):
            return {
                str(key).upper(): int(raw_value) for key, raw_value in value.items()
            }
        parsed: dict[str, int] = {}
        for segment in value.split(","):
            if not segment.strip():
                continue
            key, separator, raw_amount = segment.partition("=")
            if not separator:
                raise ValueError(
                    "IG_STREAMING_ASSET_CLASS_SLOT_BUDGETS must use ASSET=COUNT entries."
                )
            parsed[key.strip().upper()] = int(raw_amount.strip())
        return parsed

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        sqlite_prefix = "sqlite:///"
        if not value.startswith(sqlite_prefix):
            return value

        raw_path = value[len(sqlite_prefix) :]
        if raw_path in {"", ":memory:"} or raw_path.startswith("/"):
            return value

        normalized_path = (BACKEND_ROOT / raw_path.removeprefix("./")).resolve()
        return f"sqlite:///{normalized_path.as_posix()}"

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

    @field_validator(
        "market_data_poll_interval_seconds",
        "ig_streaming_watch_interval_seconds",
        "ig_streaming_stale_after_seconds",
        "ig_streaming_transition_debounce_seconds",
        "tier2_refresh_interval_seconds",
        "tier2_refresh_stale_after_seconds",
    )
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
        "ig_streaming_max_instruments",
        "ig_streaming_max_promotions_per_minute",
        "ig_streaming_min_tier1_residency_seconds",
        "ig_streaming_demotion_cooldown_seconds",
        "ig_streaming_max_subscription_churn_per_minute",
        "tier2_refresh_batch_size",
        "tier2_promotion_ttl_seconds",
        "trade_allocator_max_decisions_per_cycle",
        "trade_allocator_max_open_positions_per_instrument",
        "autonomous_candidate_instruments_per_family",
        "allocation_max_new_positions_per_cycle",
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
        "allocation_default_risk_per_trade_percent",
        "allocation_fallback_stop_distance_percent",
        "allocation_max_new_risk_per_cycle_percent",
        "allocation_max_risk_per_strategy_percent",
        "allocation_max_risk_per_family_percent",
        "allocation_max_risk_per_instrument_percent",
        "allocation_max_risk_per_currency_percent",
        "allocation_max_gross_exposure_percent",
        "allocation_under_minimum_round_up_tolerance_percent",
        "allocation_drift_warning_percent",
        "allocation_drift_critical_percent",
        "allocation_alert_concentration_warning_utilization_percent",
        "trade_allocator_signal_stale_after_seconds",
        "max_price_age_ms",
        "max_spread_pips",
        "market_status_cache_ttl_ms",
        "system_health_heartbeat_interval_seconds",
        "ig_streaming_promotion_score_threshold",
        "ig_streaming_eviction_score_threshold",
        "tier2_promotion_score_threshold",
        mode="after",
    )
    @classmethod
    def validate_positive_runtime_numeric_limits(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Runtime numeric limit settings must be greater than 0.")
        return value

    @field_validator(
        "allocation_alert_window_minutes",
        "allocation_alert_revalidation_failure_threshold",
        "allocation_alert_broker_submission_failure_threshold",
        "allocation_alert_under_minimum_rejection_threshold",
        "allocation_alert_hard_risk_block_threshold",
        mode="after",
    )
    @classmethod
    def validate_positive_allocation_alert_thresholds(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Allocation alert thresholds must be greater than 0.")
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

    @field_validator("ig_streaming_requested_frequency")
    @classmethod
    def validate_ig_streaming_requested_frequency(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized == "unlimited":
            return "unlimited"
        frequency = float(value)
        if frequency <= 0:
            raise ValueError(
                "IG_STREAMING_REQUESTED_FREQUENCY must be a positive number or 'unlimited'."
            )
        return value.strip()


@lru_cache
def get_settings() -> Settings:
    return Settings()
