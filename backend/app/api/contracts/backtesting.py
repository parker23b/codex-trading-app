from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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

    display_name: str
    provider_id: str
    instruments: list[str] = Field(min_length=1)
    timeframe: str
    start_at: datetime
    end_at: datetime
    asset_class: str
    market_type: str
    venue: str | None = None


class CsvImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str
    csv_text: str
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
    earliest_at: datetime
    latest_at: datetime
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
    earliest_at: datetime | None
    latest_at: datetime | None
    candle_count: int
    timezone_rule: str
    price_components: list[str]
    volume_available: bool
    imported_at: datetime
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


class BacktestRunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    notes: str | None = None
    strategy_identifier: str
    profile_name: str | None = None
    strategy_parameters: dict[str, Any] = Field(default_factory=dict)
    dataset_id: str
    shortlist: list[str] = Field(min_length=1)
    timeframe: str
    start_at: datetime
    end_at: datetime
    starting_capital: float = Field(gt=0)
    position_sizing_mode: str = "FIXED_UNITS"
    risk_configuration: dict[str, Any] = Field(
        default_factory=lambda: {"fixed_size": 1.0}
    )
    spread_model: str = "DATASET"
    spread_assumption: dict[str, Any] = Field(default_factory=lambda: {"value": 0.0})
    slippage_model: str = "NONE"
    slippage_assumption: dict[str, Any] = Field(default_factory=lambda: {"value": 0.0})
    fee_model: str = "NONE"
    fee_assumption: dict[str, Any] = Field(default_factory=lambda: {"value": 0.0})
    open_position_treatment: str = "CLOSE_AT_END"


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
    requested_start_at: datetime
    requested_end_at: datetime
    effective_start_at: datetime | None
    effective_end_at: datetime | None
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
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failure_reason: str | None
    result_summary: dict[str, Any]


class BacktestTradeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int
    run_id: str
    instrument: str
    direction: str
    size: float
    open_price: float
    close_price: float
    open_time: datetime
    close_time: datetime
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

    timestamp: datetime
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
    code: str
    severity: str
    message: str
    instrument: str | None
    timestamp: datetime | None
    details: dict[str, Any]
    created_at: datetime


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
