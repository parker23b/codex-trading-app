from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel

from app.api.contracts.identifiers import IdentifierProjection
from app.core.broker import OrderDirection
from app.core.risk_truth import RiskTruthConfidence
from app.models.trade import ExecutionPhase, ExecutionStatus, TradeIntentState


class AllocationAlertState(str, Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class AllocationAlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class AllocationAlertEscalationLevel(str, Enum):
    NONE = "none"
    WARNING = "warning"
    CRITICAL = "critical"


class AllocationCycleResponse(BaseModel):
    cycle_id: str
    received_at: datetime
    completed_at: datetime
    candidate_count: int
    approved_count: int
    rejected_count: int
    total_requested_risk_percent: float
    total_allocated_risk_percent: float
    remaining_portfolio_risk_percent: float
    resized_candidate_count: int
    degraded_candidate_count: int
    blocked_unsupported_sizing_count: int
    blocked_approximate_live_count: int
    blocked_under_minimum_size_count: int
    blocked_budget_count: int
    blocked_conflict_count: int
    binding_budget_counts: dict[str, int]
    rejection_reason_counts: dict[str, int]
    details: dict[str, Any]
    intents: list["AllocationIntentResponse"] | None = None


class AllocationIntentExecutionResponse(BaseModel):
    id: int
    phase: ExecutionPhase | str
    status: ExecutionStatus | str
    client_request_id: IdentifierProjection | None
    broker_reference: IdentifierProjection | None
    submitted_at: datetime | None
    acknowledged_at: datetime | None
    completed_at: datetime | None
    requested_size: float | None
    filled_size: float | None
    requested_price: float | None
    average_fill_price: float | None
    intended_risk_amount: float | None
    submitted_risk_amount: float | None
    fill_derived_risk_amount: float | None
    risk_truth_confidence: RiskTruthConfidence | None
    reason: str | None
    error_code: str | None
    error_message: str | None
    requires_manual_review: bool
    details: dict[str, Any]


class AllocationIntentPositionResponse(BaseModel):
    id: int
    broker_reference: IdentifierProjection | None
    instrument: str
    direction: OrderDirection | str
    size: float
    open_price: float
    current_price: float | None
    unrealized_pnl: float | None
    risk_percent: float | None
    entry_risk_amount: float | None
    risk_truth_confidence: RiskTruthConfidence | None
    open_time: datetime
    close_time: datetime | None
    is_open: bool


class AllocationIntentTradeResponse(BaseModel):
    id: int
    broker_reference: IdentifierProjection | None
    close_broker_reference: IdentifierProjection | None
    instrument: str
    direction: OrderDirection | str
    size: float
    open_price: float
    close_price: float
    pnl: float
    entry_risk_amount: float | None
    risk_truth_confidence: RiskTruthConfidence | None
    r_multiple: float | None
    open_time: datetime
    close_time: datetime
    reason: str | None
    outcome: str | None


class AllocationIntentResponse(BaseModel):
    id: int
    allocation_cycle_id: str | None
    strategy_name: str
    family_name: str | None
    instrument: str
    direction: OrderDirection | str
    state: TradeIntentState | str
    signal_time: datetime
    decision_reason_code: str | None
    decision_reason: str | None
    close_reason_code: str | None
    close_reason: str | None
    proposed_size: float | None
    allocated_size: float | None
    proposed_risk_percent: float | None
    allocated_risk_percent: float | None
    confidence: float | None
    estimated_risk_amount: float | None
    submitted_risk_amount: float | None
    fill_derived_risk_amount: float | None
    risk_truth_confidence: RiskTruthConfidence | None
    risk_currency: str | None
    allocation: dict[str, Any]
    allocation_outcome: dict[str, Any]
    risk_tracking: dict[str, Any]
    risk_reconciliation: dict[str, Any]
    latest_execution: AllocationIntentExecutionResponse | None
    executions: list[AllocationIntentExecutionResponse]
    position: AllocationIntentPositionResponse | None
    trade: AllocationIntentTradeResponse | None
    details: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class AllocationDriftIntentSummaryResponse(BaseModel):
    trade_intent_id: int
    strategy_name: str
    family_name: str | None
    instrument: str
    state: TradeIntentState | str
    max_percent_drift: float
    drift_metrics: dict[str, Any]
    updated_at: datetime


class AllocationDriftBucketResponse(BaseModel):
    name: str
    count: int
    average_percent_drift: float
    max_percent_drift: float


class AllocationDriftSummaryResponse(BaseModel):
    window_minutes: int
    drift_warning_percent: float
    drift_critical_percent: float
    material_drift_count: int
    worst_intents: list[AllocationDriftIntentSummaryResponse]
    by_strategy: list[AllocationDriftBucketResponse]
    by_family: list[AllocationDriftBucketResponse]
    by_instrument: list[AllocationDriftBucketResponse]


class AllocationAlertResponse(BaseModel):
    id: int
    alert_key: str
    alert_type: str
    severity: AllocationAlertSeverity | str
    state: AllocationAlertState | str
    escalation_level: AllocationAlertEscalationLevel | str
    title: str
    message: str | None
    count: int
    recurrence_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    related_intent_ids: list[int]
    related_cycle_ids: list[str]
    related_execution_ids: list[int]
    details: dict[str, Any]


class AllocationAlertMutationResponse(BaseModel):
    id: int
    state: AllocationAlertState | str
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None


class AllocationExposureTotalsResponse(BaseModel):
    reserved_risk_percent: float
    live_risk_percent: float
    provisional_live_risk_percent: float
    reserved_risk_amount: float
    live_risk_amount: float
    provisional_live_risk_amount: float
    reserved_intent_count: int
    open_position_count: int
    remaining_portfolio_risk_percent: float


class ExposureBucketResponse(BaseModel):
    name: str
    bucket_type: str
    reserved_risk_percent: float
    live_risk_percent: float
    reserved_risk_amount: float
    live_risk_amount: float
    reserved_count: int
    live_count: int
    budget_limit_percent: float
    total_risk_percent: float
    utilization_percent: float | None
    remaining_risk_percent: float
    risk_basis: list[str]


class DirectionalCurrencyExposureBucketResponse(BaseModel):
    currency: str
    reserved_long_risk_percent: float
    reserved_short_risk_percent: float
    live_long_risk_percent: float
    live_short_risk_percent: float
    reserved_long_risk_amount: float
    reserved_short_risk_amount: float
    live_long_risk_amount: float
    live_short_risk_amount: float
    gross_risk_percent: float
    net_risk_percent: float
    gross_utilization_percent: float
    net_bias: str
    risk_basis: list[str]


class ExposureHotspotResponse(BaseModel):
    bucket_type: str
    name: str
    total_risk_percent: float
    budget_limit_percent: float
    utilization_percent: float
    risk_basis: list[str]
    bucket_mode: str
    net_bias: str | None = None
    net_risk_percent: float | None = None


class AllocationExposureSummaryResponse(BaseModel):
    totals: AllocationExposureTotalsResponse
    by_strategy: list[ExposureBucketResponse]
    by_family: list[ExposureBucketResponse]
    by_instrument: list[ExposureBucketResponse]
    by_currency: list[ExposureBucketResponse]
    currency_directional: list[DirectionalCurrencyExposureBucketResponse]
    hotspots: list[ExposureHotspotResponse]
    notes: dict[str, str]
