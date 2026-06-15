from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    model_validator,
)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Backend response timestamp must be timezone-aware.")
    return value.astimezone(UTC)


UtcDateTime = Annotated[datetime, AfterValidator(_as_utc)]


class HistoricalProviderCapabilitiesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str
    venue: str
    supported_asset_classes: list[str] | tuple[str, ...]
    supported_market_types: list[str] | tuple[str, ...]
    available_timeframes: list[str] | tuple[str, ...]
    midpoint_ohlc: bool
    bid_ohlc: bool
    ask_ohlc: bool
    trade_price_ohlc: bool
    volume: bool
    spread_must_be_simulated: bool
    maximum_records_per_request: int | None
    authentication: str
    instrument_mapping_examples: dict[str, str]
    quota_warnings: list[str] | tuple[str, ...]
    configured: bool
    configuration_warning: str | None = None


class ProviderImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1)
    provider_id: str
    instruments: list[str] = Field(min_length=1)
    timeframe: str
    start_at: AwareDatetime
    end_at: AwareDatetime
    asset_class: str
    market_type: str
    venue: str | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "ProviderImportRequest":
        if self.start_at >= self.end_at:
            raise ValueError("Historical import start must be before end.")
        return self


class CsvImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1)
    csv_text: str = Field(min_length=1)
    asset_class: str
    venue: str
    market_type: str
    source_identifier: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)


class HistoricalDatasetPartitionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int
    dataset_id: str
    instrument: str
    provider_instrument: str
    timeframe: str
    earliest_at: UtcDateTime
    latest_at: UtcDateTime
    candle_count: int
    price_components: list[str]
    volume_available: bool
    checksum: str
    detected_gaps: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    source_metadata: dict[str, Any]


class HistoricalDatasetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str
    display_name: str
    provider: str
    source_identifier: str | None
    venue: str
    market_type: str
    asset_class: str
    base_timeframe: str
    status: str
    availability: str
    availability_reason: str | None
    availability_updated_at: UtcDateTime | None
    selectable: bool
    earliest_at: UtcDateTime | None
    latest_at: UtcDateTime | None
    candle_count: int
    timezone_rule: str
    price_components: list[str]
    volume_available: bool
    imported_at: UtcDateTime
    checksum: str | None
    completeness_status: str
    detected_gaps: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    source_metadata: dict[str, Any]
    import_parameters: dict[str, Any]
    failure_reason: str | None
    storage_format: str
    immutable: bool
    partitions: list[HistoricalDatasetPartitionResponse] = Field(default_factory=list)


class ExecutionAssumptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: FiniteFloat = Field(default=0.0, ge=0)


class BacktestRunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    notes: str | None = None
    strategy_identifier: str
    profile_name: str | None = None
    strategy_parameters: dict[str, FiniteFloat] = Field(default_factory=dict)
    dataset_id: str
    shortlist: list[str] = Field(min_length=1)
    timeframe: Literal["S5", "1m", "M1", "5m", "M5", "15m", "M15", "30m", "1h", "H1"]
    start_at: AwareDatetime
    end_at: AwareDatetime
    starting_capital: FiniteFloat = Field(gt=0)
    position_sizing_mode: Literal["FIXED_UNITS", "PERCENT_RISK"] = "FIXED_UNITS"
    risk_configuration: dict[str, FiniteFloat] = Field(
        default_factory=lambda: {"fixed_size": 1.0}
    )
    spread_model: Literal["DATASET", "FIXED_PRICE", "FIXED_BPS", "NONE"] = "DATASET"
    spread_assumption: ExecutionAssumptionRequest = Field(
        default_factory=ExecutionAssumptionRequest
    )
    slippage_model: Literal["NONE", "FIXED_PRICE", "FIXED_BPS"] = "NONE"
    slippage_assumption: ExecutionAssumptionRequest = Field(
        default_factory=ExecutionAssumptionRequest
    )
    fee_model: Literal["NONE", "FIXED_PER_ORDER", "PER_UNIT", "BPS_NOTIONAL"] = "NONE"
    fee_assumption: ExecutionAssumptionRequest = Field(
        default_factory=ExecutionAssumptionRequest
    )
    open_position_treatment: Literal["CLOSE_AT_END", "MARK_TO_MARKET"] = "CLOSE_AT_END"

    @model_validator(mode="after")
    def validate_configuration(self) -> "BacktestRunCreateRequest":
        if self.start_at >= self.end_at:
            raise ValueError("Backtest start must be before end.")
        if len(set(self.shortlist)) != len(self.shortlist):
            raise ValueError("Backtest shortlist cannot contain duplicates.")
        max_open_positions = self.risk_configuration.get("max_open_positions", 1)
        if max_open_positions <= 0 or not float(max_open_positions).is_integer():
            raise ValueError("max_open_positions must be a positive whole number.")
        if self.position_sizing_mode == "FIXED_UNITS":
            if self.risk_configuration.get("fixed_size", 0) <= 0:
                raise ValueError("fixed_size must be positive.")
        else:
            risk_percent = self.risk_configuration.get("risk_per_trade_percent", 0)
            if risk_percent <= 0 or risk_percent > 100:
                raise ValueError(
                    "risk_per_trade_percent must be greater than 0 and at most 100."
                )
            if self.risk_configuration.get("fallback_stop_percent", 0) <= 0:
                raise ValueError("fallback_stop_percent must be positive.")
            max_size = self.risk_configuration.get("max_size")
            if max_size is not None and max_size <= 0:
                raise ValueError("max_size must be positive.")
        return self


class BacktestRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str
    name: str | None
    notes: str | None
    strategy_identifier: str
    strategy_version: str
    strategy_configuration: dict[str, Any]
    dataset_id: str
    dataset_checksum: str
    shortlist: list[str]
    timeframe: str
    requested_start_at: UtcDateTime
    requested_end_at: UtcDateTime
    effective_start_at: UtcDateTime | None
    effective_end_at: UtcDateTime | None
    starting_capital: float
    position_sizing_mode: str
    risk_configuration: dict[str, Any]
    spread_model: str
    spread_assumption: dict[str, Any]
    slippage_model: str
    slippage_assumption: dict[str, Any]
    fee_model: str
    fee_assumption: dict[str, Any]
    open_position_treatment: str
    pricing_mode: str
    evaluation_boundary: str
    status: str
    created_at: UtcDateTime
    started_at: UtcDateTime | None
    completed_at: UtcDateTime | None
    failure_reason: str | None
    result_manifest_version: str | None
    result_checksum: str | None
    result_summary: dict[str, Any]


class BacktestTradeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int
    run_id: str
    deterministic_sequence: int
    instrument: str
    direction: str
    size: float
    open_price: float
    close_price: float
    open_time: UtcDateTime
    close_time: UtcDateTime
    gross_pnl: float
    fees: float
    spread_cost: float
    slippage_cost: float
    net_pnl: float
    exit_reason: str
    stop_loss_price: float | None
    take_profit_price: float | None
    conservative_ambiguity: bool
    pricing_mode: str
    details: dict[str, Any]


class BacktestEquityPointResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    timestamp: UtcDateTime
    cash: float
    unrealized_pnl: float
    equity: float
    drawdown: float
    drawdown_percent: float
    open_position_count: int


class BacktestWarningResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int
    run_id: str
    deterministic_sequence: int
    code: str
    severity: str
    message: str
    instrument: str | None
    timestamp: UtcDateTime | None
    details: dict[str, Any]
    created_at: UtcDateTime


class BacktestMetricsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run: dict[str, Any]
    by_instrument: dict[str, dict[str, Any]]


class BacktestInstrumentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    instrument: str
    provider_instrument: str
    dataset_partition_id: int
    candle_count: int
    metrics: dict[str, Any]
