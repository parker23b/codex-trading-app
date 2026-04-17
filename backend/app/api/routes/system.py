from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings
from app.strategies.registry import strategy_registry

router = APIRouter()


class RiskLimitsResponse(BaseModel):
    max_open_positions: int
    max_positions_per_strategy: int
    max_open_risk_percent: float
    daily_loss_limit: float
    max_position_notional: float
    max_unhealthy_runtimes: int
    global_entry_kill_switch: bool


class ExecutionLimitsResponse(BaseModel):
    max_price_age_ms: float
    max_spread_pips: float
    max_spread_percent_of_price: float
    entry_burst_limit: int
    entry_burst_window_seconds: int
    failed_entry_retry_cooldown_seconds: int
    duplicate_signal_window_seconds: int
    cooldown_after_loss_seconds: int
    cooldown_after_exit_seconds: int
    allocator_enabled: bool
    allocator_signal_stale_after_seconds: float
    allocation_default_risk_per_trade_percent: float
    allocation_fallback_stop_distance_percent: float
    allocation_max_new_positions_per_cycle: int
    allocation_max_new_risk_per_cycle_percent: float
    allocation_max_risk_per_strategy_percent: float
    allocation_max_risk_per_family_percent: float
    allocation_max_risk_per_instrument_percent: float
    allocation_max_risk_per_currency_percent: float
    allocation_max_gross_exposure_percent: float
    allocation_under_minimum_round_up_tolerance_percent: float


class CoverageLimitsResponse(BaseModel):
    streaming_enabled: bool
    max_instruments: int
    requested_frequency: str
    max_promotions_per_minute: int
    max_subscription_churn_per_minute: int
    promotion_score_threshold: float
    eviction_score_threshold: float
    min_tier1_residency_seconds: int
    demotion_cooldown_seconds: int
    tier2_refresh_enabled: bool
    tier2_refresh_interval_seconds: float
    tier2_refresh_batch_size: int
    tier2_refresh_stale_after_seconds: float
    tier2_promotion_score_threshold: float
    tier2_promotion_ttl_seconds: int
    asset_class_slot_budgets: dict[str, int]
    seed_instruments: list[str]
    tier2_seed_instruments: list[str]


class ScreeningStrategySummaryResponse(BaseModel):
    name: str
    description: str
    promotion_threshold: float
    refresh_tier: str


class SystemOperatingLimitsResponse(BaseModel):
    autonomous_control_enabled: bool
    risk: RiskLimitsResponse
    execution: ExecutionLimitsResponse
    coverage: CoverageLimitsResponse
    screening: list[ScreeningStrategySummaryResponse]


@router.get("/system/limits", response_model=SystemOperatingLimitsResponse)
def get_system_operating_limits() -> SystemOperatingLimitsResponse:
    settings = get_settings()
    return SystemOperatingLimitsResponse(
        autonomous_control_enabled=settings.autonomous_control_enabled,
        risk=RiskLimitsResponse(
            max_open_positions=settings.runtime_max_open_positions,
            max_positions_per_strategy=settings.runtime_max_positions_per_strategy,
            max_open_risk_percent=settings.runtime_max_open_risk_percent,
            daily_loss_limit=settings.runtime_daily_loss_limit,
            max_position_notional=settings.runtime_max_position_notional,
            max_unhealthy_runtimes=settings.runtime_max_unhealthy_runtimes,
            global_entry_kill_switch=settings.runtime_global_entry_kill_switch,
        ),
        execution=ExecutionLimitsResponse(
            max_price_age_ms=settings.max_price_age_ms,
            max_spread_pips=settings.max_spread_pips,
            max_spread_percent_of_price=settings.runtime_max_spread_percent_of_price,
            entry_burst_limit=settings.runtime_entry_burst_limit,
            entry_burst_window_seconds=settings.runtime_entry_burst_window_seconds,
            failed_entry_retry_cooldown_seconds=settings.runtime_failed_entry_retry_cooldown_seconds,
            duplicate_signal_window_seconds=settings.runtime_duplicate_signal_window_seconds,
            cooldown_after_loss_seconds=settings.runtime_cooldown_after_loss_seconds,
            cooldown_after_exit_seconds=settings.runtime_cooldown_after_exit_seconds,
            allocator_enabled=settings.allocation_enabled,
            allocator_signal_stale_after_seconds=settings.trade_allocator_signal_stale_after_seconds,
            allocation_default_risk_per_trade_percent=settings.allocation_default_risk_per_trade_percent,
            allocation_fallback_stop_distance_percent=settings.allocation_fallback_stop_distance_percent,
            allocation_max_new_positions_per_cycle=settings.allocation_max_new_positions_per_cycle,
            allocation_max_new_risk_per_cycle_percent=settings.allocation_max_new_risk_per_cycle_percent,
            allocation_max_risk_per_strategy_percent=settings.allocation_max_risk_per_strategy_percent,
            allocation_max_risk_per_family_percent=settings.allocation_max_risk_per_family_percent,
            allocation_max_risk_per_instrument_percent=settings.allocation_max_risk_per_instrument_percent,
            allocation_max_risk_per_currency_percent=settings.allocation_max_risk_per_currency_percent,
            allocation_max_gross_exposure_percent=settings.allocation_max_gross_exposure_percent,
            allocation_under_minimum_round_up_tolerance_percent=settings.allocation_under_minimum_round_up_tolerance_percent,
        ),
        coverage=CoverageLimitsResponse(
            streaming_enabled=settings.ig_streaming_enabled,
            max_instruments=settings.ig_streaming_max_instruments,
            requested_frequency=settings.ig_streaming_requested_frequency,
            max_promotions_per_minute=settings.ig_streaming_max_promotions_per_minute,
            max_subscription_churn_per_minute=settings.ig_streaming_max_subscription_churn_per_minute,
            promotion_score_threshold=settings.ig_streaming_promotion_score_threshold,
            eviction_score_threshold=settings.ig_streaming_eviction_score_threshold,
            min_tier1_residency_seconds=settings.ig_streaming_min_tier1_residency_seconds,
            demotion_cooldown_seconds=settings.ig_streaming_demotion_cooldown_seconds,
            tier2_refresh_enabled=settings.tier2_refresh_enabled,
            tier2_refresh_interval_seconds=settings.tier2_refresh_interval_seconds,
            tier2_refresh_batch_size=settings.tier2_refresh_batch_size,
            tier2_refresh_stale_after_seconds=settings.tier2_refresh_stale_after_seconds,
            tier2_promotion_score_threshold=settings.tier2_promotion_score_threshold,
            tier2_promotion_ttl_seconds=settings.tier2_promotion_ttl_seconds,
            asset_class_slot_budgets=settings.ig_streaming_asset_class_slot_budgets,
            seed_instruments=settings.ig_streaming_seed_instruments,
            tier2_seed_instruments=settings.tier2_seed_instruments,
        ),
        screening=[
            ScreeningStrategySummaryResponse(
                name=metadata.name,
                description=metadata.description,
                promotion_threshold=metadata.promotion_threshold,
                refresh_tier=metadata.refresh_tier,
            )
            for metadata in strategy_registry.list_screening_metadata()
        ],
    )
