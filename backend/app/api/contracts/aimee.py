from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.routes.events import DomainEventResponse
from app.api.routes.health import OperationalTelemetryResponse
from app.reviewer.models import OperatorSummaryReview, ReviewRecordSummary


class AimeeControlPlaneGovernanceSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_state: str
    autonomous_operation_allowed: bool
    emergency_stop: bool


class AimeeControlPlaneDeploymentSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str
    open_risk_management_state: str | None = None
    open_risk_management_reason: str | None = None
    blocked_reason: str | None = None
    degraded_reason: str | None = None
    selected_instrument: str | None = None
    selected_profile: str | None = None
    updated_at: datetime | None = None


class AimeeControlPlaneRuntimeSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_running: bool
    active_instrument: str | None = None
    active_profile_name: str | None = None
    control_mode: str | None = None
    persisted_runtime_count: int


class AimeeControlPlaneAlignmentSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_aligned: bool | None
    reason: str


class AimeeControlPlaneFamilySummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_name: str
    deployment: AimeeControlPlaneDeploymentSummaryResponse | None = None
    runtime: AimeeControlPlaneRuntimeSummaryResponse
    alignment: AimeeControlPlaneAlignmentSummaryResponse
    governance: AimeeControlPlaneGovernanceSummaryResponse


class AimeeControlPlaneSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    effective_autonomous_control_enabled: bool
    configured_autonomous_control_enabled: bool
    autonomy_override_active: bool
    autonomy_override_value: bool | None = None
    autonomy_override_reason: str | None = None
    autonomy_updated_at: datetime | None = None
    feed_source_state: str
    feed_health_state: str
    broker_connectivity_state: str
    entry_eligible: bool
    exit_eligible: bool
    entry_block_reason: str | None = None
    exit_block_reason: str | None = None
    open_risk_management_state: str
    open_risk_management_reason: str | None = None
    misaligned_count: int
    counts: dict[str, int] = Field(default_factory=dict)
    families: list[AimeeControlPlaneFamilySummaryResponse] = Field(default_factory=list)


class AimeeCoverageStreamingSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_instruments: list[str] = Field(default_factory=list)
    desired_instruments: list[str] = Field(default_factory=list)
    pinned_instruments: list[str] = Field(default_factory=list)
    capped_instruments: list[str] = Field(default_factory=list)
    asset_class_usage: dict[str, int] = Field(default_factory=dict)


class AimeeCoveragePromotionSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pending_count: int
    accepted_count: int
    rejected_count: int
    expired_count: int


class AimeeCoverageTradeAllocatorSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_count: int
    rejected_count: int
    reason_counts: dict[str, int] = Field(default_factory=dict)


class AimeeCoverageSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    streaming: AimeeCoverageStreamingSummaryResponse
    promotions: AimeeCoveragePromotionSummaryResponse
    trade_allocator: AimeeCoverageTradeAllocatorSummaryResponse


class AimeeStrategySummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: Literal["RUNNING", "STOPPED"]
    warning_message: str | None = None


class AimeeSnapshotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review: OperatorSummaryReview
    history: list[ReviewRecordSummary] = Field(default_factory=list)
    controlPlane: AimeeControlPlaneSummaryResponse
    coverage: AimeeCoverageSummaryResponse
    telemetry: OperationalTelemetryResponse
    events: list[DomainEventResponse] = Field(default_factory=list)
    strategies: list[AimeeStrategySummaryResponse] = Field(default_factory=list)
    updatedAt: datetime
