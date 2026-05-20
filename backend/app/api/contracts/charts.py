from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from app.core.risk_truth import RiskTruthConfidence


class RiskAllocationChartDataStatus(str, Enum):
    READY = "READY"
    PARTIAL = "PARTIAL"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class RiskAllocationChartSource(str, Enum):
    ALLOCATION_EXPOSURE_SUMMARY_PLUS_POSITION_INTENT_TRUTH = (
        "ALLOCATION_EXPOSURE_SUMMARY_PLUS_POSITION_INTENT_TRUTH"
    )


class RiskAllocationTruthCountResponse(BaseModel):
    confidence: RiskTruthConfidence | str
    count: int


class RiskAllocationChartSummaryResponse(BaseModel):
    reserved_risk_percent: float | None
    live_risk_percent: float | None
    provisional_live_risk_percent: float | None
    total_active_risk_percent: float | None
    remaining_portfolio_risk_percent: float | None
    reserved_intent_count: int
    open_position_count: int
    chartable_bucket_count: int
    unavailable_bucket_count: int
    has_provisional_risk: bool
    has_simulated_risk: bool
    has_unknown_risk: bool
    has_degraded_risk: bool
    risk_truth_confidence_mix: list[RiskAllocationTruthCountResponse]
    reasons: list[str]


class RiskAllocationChartBucketResponse(BaseModel):
    instrument: str
    reserved_risk_percent: float | None
    live_risk_percent: float | None
    provisional_live_risk_percent: float | None
    total_risk_percent: float | None
    utilization_percent: float | None
    budget_limit_percent: float
    reserved_intent_count: int
    open_position_count: int
    data_status: RiskAllocationChartDataStatus | str
    has_provisional_risk: bool
    has_simulated_risk: bool
    has_unknown_risk: bool
    has_degraded_risk: bool
    risk_basis: list[str]
    risk_truth_confidence_mix: list[RiskAllocationTruthCountResponse]
    reasons: list[str]


class RiskAllocationChartResponse(BaseModel):
    generated_at: datetime
    data_status: RiskAllocationChartDataStatus | str
    source: RiskAllocationChartSource | str
    chart_mode: str
    summary: RiskAllocationChartSummaryResponse
    bars: list[RiskAllocationChartBucketResponse]
    reasons: list[str]
    notes: dict[str, str]
