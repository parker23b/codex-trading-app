from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.contracts.identifiers import IdentifierProjection


class StrategyRuntimeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_name: str
    instrument: str
    runtime_key: str
    has_open_position: bool
    broker_reference: IdentifierProjection | None = None
    direction: Literal["BUY", "SELL"] | None = None
    current_price: float | None = None
    unrealized_pnl: float | None = None
    recovery_state: str | None = None
    runtime_mode: str | None = None
    control_mode: str | None = None
    deployment_id: int | None = None
    recovery_reason: str | None = None


class StrategyPositionSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    broker_reference: IdentifierProjection | None = None
    instrument: str
    direction: Literal["BUY", "SELL"]
    size: float
    open_price: float
    current_price: float | None = None
    unrealized_pnl: float | None = None
    risk_percent: float | None = None


class StrategyPersistedRuntimeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: IdentifierProjection
    instrument: str
    status: str
    recovery_state: str | None = None
    recovery_reason: str | None = None
    last_heartbeat_at: datetime | None = None
    last_price_seen: float | None = None
    last_price_seen_at: datetime | None = None
    control_mode: str | None = None
    runtime_mode: str | None = None
    deployment_id: int | None = None
    active_profile_name: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    auto_resume: bool | None = None


class StrategyInstrumentOptionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    epic: str
    label: str
    category: str


class StrategyParameterResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    value: float
    step: float | None = None


class StrategySummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    instrument: str
    status: Literal["RUNNING", "STOPPED"]
    current_pnl: float
    last_price: float | None = None
    price_status: str | None = None
    price_error: str | None = None
    last_price_updated_at: datetime | None = None
    trade_count: int
    win_rate: float
    account_type: str
    position_size: float
    risk_per_trade: float
    supported_asset_classes: list[str] = Field(default_factory=list)
    available_profiles: list[str] = Field(default_factory=list)
    governance_approval_state: str
    autonomous_operation_allowed: bool
    authorized: bool
    emergency_stop: bool
    deployment_state: str
    deployment_profile: str | None = None
    deployment_parameters: dict[str, Any] = Field(default_factory=dict)
    deployment_instrument: str | None = None
    deployment_reason: str | None = None
    active_instruments: list[str] = Field(default_factory=list)
    evaluating_instrument_count: int
    candidates_generated_today: int
    candidates_promoted_today: int
    candidates_blocked_today: int
    active_runtime_count: int
    open_position_count: int
    warning_message: str | None = None
    warning_instrument: str | None = None
    warning_status: str | None = None
    active_runtimes: list[StrategyRuntimeResponse] = Field(default_factory=list)
    open_positions: list[StrategyPositionSummaryResponse] = Field(default_factory=list)
    persisted_runtimes: list[StrategyPersistedRuntimeResponse] = Field(
        default_factory=list
    )
    instrument_options: list[StrategyInstrumentOptionResponse] = Field(
        default_factory=list
    )
    parameters: list[StrategyParameterResponse] = Field(default_factory=list)
