from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.contracts.identifiers import IdentifierProjection


class ControlPlaneAlignmentCheckResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    passed: bool
    expected: Any | None = None
    actual: Any | None = None


class ControlPlaneRecentEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    created_at: datetime
    event_type: str
    title: str
    message: str | None = None
    severity: str
    payload_json: dict[str, Any] = Field(default_factory=dict)


class ControlPlaneGovernanceSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_state: str
    autonomous_operation_allowed: bool
    emergency_stop: bool
    approved_asset_classes: list[str] = Field(default_factory=list)
    approved_instruments: list[str] = Field(default_factory=list)
    approved_profile_names: list[str] = Field(default_factory=list)
    supported_asset_classes: list[str] = Field(default_factory=list)
    available_profile_names: list[str] = Field(default_factory=list)
    max_concurrent_deployments: int | None = None
    notes: str | None = None
    updated_at: datetime | None = None


class ControlPlaneDeploymentSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str
    open_risk_management_state: str | None = None
    open_risk_management_reason: str | None = None
    selected_profile: str | None = None
    selected_profile_parameters: dict[str, Any] = Field(default_factory=dict)
    selected_instrument: str | None = None
    selected_asset_class: str | None = None
    suitability_score: float | None = None
    suitability_reason: str | None = None
    profile_selected_at: datetime | None = None
    profile_change_reason: str | None = None
    last_restart_reason: str | None = None
    blocked_reason: str | None = None
    degraded_reason: str | None = None
    last_evaluated_at: datetime | None = None
    last_deployed_at: datetime | None = None
    updated_at: datetime | None = None


class ControlPlanePersistedRuntimeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: IdentifierProjection
    status: str
    instrument: str
    control_mode: str | None = None
    runtime_mode: str | None = None
    active_profile_name: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime | None = None


class ControlPlaneRuntimeSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_running: bool
    active_runtime_id: IdentifierProjection | None = None
    active_instrument: str | None = None
    active_profile_name: str | None = None
    active_parameters: dict[str, Any] = Field(default_factory=dict)
    control_mode: str | None = None
    runtime_mode: str | None = None
    recovery_state: str | None = None
    updated_at: datetime | None = None
    persisted_runtimes: list[ControlPlanePersistedRuntimeResponse] = Field(
        default_factory=list
    )


class ControlPlaneAlignmentSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_aligned: bool | None
    status: str
    reason: str
    checks: list[ControlPlaneAlignmentCheckResponse] = Field(default_factory=list)


class ControlPlaneFamilyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_name: str
    description: str
    supported_asset_classes: list[str] = Field(default_factory=list)
    available_profile_names: list[str] = Field(default_factory=list)
    governance: ControlPlaneGovernanceSummaryResponse
    deployment: ControlPlaneDeploymentSummaryResponse | None = None
    runtime: ControlPlaneRuntimeSummaryResponse
    alignment: ControlPlaneAlignmentSummaryResponse
    recent_events: list[ControlPlaneRecentEventResponse] = Field(default_factory=list)


class ControlPlaneSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    autonomous_control_enabled: bool
    configured_autonomous_control_enabled: bool
    effective_autonomous_control_enabled: bool
    autonomy_override_active: bool
    autonomy_override_value: bool | None = None
    autonomy_override_reason: str | None = None
    autonomy_updated_at: datetime | None = None
    feed_source_state: str
    feed_health_state: str
    broker_connectivity_state: str
    entry_eligible: bool
    exit_eligible: bool
    entry_eligibility_state: str | None = None
    exit_eligibility_state: str | None = None
    entry_block_reason: str | None = None
    exit_block_reason: str | None = None
    open_risk_management_state: str
    open_risk_management_reason: str | None = None
    open_risk_authority_version: int | None = None
    open_risk_authority_updated_at: datetime | None = None
    open_risk_reconciliation_status: str | None = None
    families: list[ControlPlaneFamilyResponse] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    misaligned_count: int


class OperatorControlResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    configured_autonomous_control_enabled: bool
    effective_autonomous_control_enabled: bool
    override_active: bool
    override_value: bool | None = None
    override_reason: str | None = None
    updated_at: datetime | None = None


class GovernanceMutationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_name: str
    approval_state: str
    autonomous_operation_allowed: bool
    emergency_stop: bool
    approved_asset_classes: list[str] = Field(default_factory=list)
    approved_instruments: list[str] = Field(default_factory=list)
    approved_profile_names: list[str] = Field(default_factory=list)
    max_concurrent_deployments: int
    notes: str | None = None
    updated_at: datetime


class ControlPlaneReconcileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deployed: int
    paused: int
    blocked: int
    degraded: int
    emergency_stopped: int


class StrategyMutationStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["started", "stopped"]
    strategy: str | None = None
    instrument: str | None = None
