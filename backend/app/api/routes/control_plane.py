from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.db.session import get_session
from app.models.strategy_governance import GovernanceApprovalState
from app.services.control_plane_service import ControlPlaneService
from app.services.domain_event_service import domain_event_service
from app.services.operator_control_service import OperatorControlService
from app.services.strategy_deployment_manager_service import (
    StrategyDeploymentManagerService,
)
from app.services.strategy_governance_service import StrategyGovernanceService

router = APIRouter()


class GovernanceUpdateRequest(BaseModel):
    approval_state: str | None = Field(default=None)
    autonomous_operation_allowed: bool | None = Field(default=None)
    emergency_stop: bool | None = Field(default=None)
    approved_asset_classes: list[str] | None = Field(default=None)
    approved_instruments: list[str] | None = Field(default=None)
    approved_profile_names: list[str] | None = Field(default=None)
    max_concurrent_deployments: int | None = Field(default=None, ge=1)
    notes: str | None = Field(default=None)


class ControlPlaneSummaryResponse(BaseModel):
    autonomous_control_enabled: bool
    configured_autonomous_control_enabled: bool
    effective_autonomous_control_enabled: bool
    autonomy_override_active: bool
    autonomy_override_value: bool | None
    autonomy_override_reason: str | None
    autonomy_updated_at: datetime | None
    feed_source_state: str
    feed_health_state: str
    broker_connectivity_state: str
    entry_eligible: bool
    exit_eligible: bool
    entry_block_reason: str | None
    exit_block_reason: str | None
    open_risk_management_state: str
    open_risk_management_reason: str | None
    families: list[dict[str, object]]
    counts: dict[str, int]
    misaligned_count: int


class OperatorControlResponse(BaseModel):
    configured_autonomous_control_enabled: bool
    effective_autonomous_control_enabled: bool
    override_active: bool
    override_value: bool | None
    override_reason: str | None
    updated_at: datetime | None


class OperatorControlUpdateRequest(BaseModel):
    autonomous_control_enabled: bool | None = Field(default=None)
    reason: str | None = Field(default=None)


@router.get("/control-plane/summary", response_model=ControlPlaneSummaryResponse)
def get_control_plane_summary(
    session: Session = Depends(get_session),
) -> ControlPlaneSummaryResponse:
    return ControlPlaneSummaryResponse(**ControlPlaneService(session).get_summary())


@router.get("/control-plane/operator-state", response_model=OperatorControlResponse)
def get_operator_control_state(
    session: Session = Depends(get_session),
) -> OperatorControlResponse:
    return OperatorControlResponse(**OperatorControlService(session).get_summary())


@router.put("/control-plane/operator-state", response_model=OperatorControlResponse)
def update_operator_control_state(
    payload: OperatorControlUpdateRequest,
    session: Session = Depends(get_session),
) -> OperatorControlResponse:
    state = OperatorControlService(session).update_autonomous_control(
        enabled=payload.autonomous_control_enabled,
        reason=payload.reason,
    )
    domain_event_service.record_event(
        event_type="operator.autonomy_override_updated",
        category="operator",
        severity="info",
        source="api.control_plane.update_operator_state",
        title="Autonomous control override updated",
        message="Operator updated the global autonomous control override.",
        actor_type="operator",
        actor_id="api",
        payload_json={
            "autonomous_control_override": state.autonomous_control_override,
            "override_reason": state.override_reason,
        },
    )
    return OperatorControlResponse(**OperatorControlService(session).get_summary())


@router.get("/control-plane/strategies/{strategy_name}")
def get_control_plane_strategy_detail(
    strategy_name: str,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return ControlPlaneService(session).get_family_detail(strategy_name)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.post("/control-plane/reconcile")
def reconcile_control_plane(session: Session = Depends(get_session)) -> dict[str, int]:
    result = StrategyDeploymentManagerService(session).reconcile()
    domain_event_service.record_event(
        event_type="control_plane.reconciled",
        category="strategy",
        severity="info",
        source="api.control_plane.reconcile",
        title="Control plane reconciliation completed",
        message="Autonomous deployment manager completed a reconciliation cycle.",
        actor_type="operator",
        actor_id="api",
        payload_json={
            "deployed": result.deployed,
            "paused": result.paused,
            "blocked": result.blocked,
            "degraded": result.degraded,
            "emergency_stopped": result.emergency_stopped,
        },
    )
    return {
        "deployed": result.deployed,
        "paused": result.paused,
        "blocked": result.blocked,
        "degraded": result.degraded,
        "emergency_stopped": result.emergency_stopped,
    }


@router.put("/control-plane/governance/{strategy_name}")
def update_strategy_governance(
    strategy_name: str,
    payload: GovernanceUpdateRequest,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    if payload.approval_state is not None and payload.approval_state not in {
        GovernanceApprovalState.NOT_APPROVED.value,
        GovernanceApprovalState.APPROVED.value,
        GovernanceApprovalState.DISABLED.value,
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid approval_state."
        )
    try:
        record = StrategyGovernanceService(session).upsert_strategy(
            strategy_name=strategy_name,
            approval_state=payload.approval_state,
            autonomous_operation_allowed=payload.autonomous_operation_allowed,
            emergency_stop=payload.emergency_stop,
            approved_asset_classes=payload.approved_asset_classes,
            approved_instruments=payload.approved_instruments,
            approved_profile_names=payload.approved_profile_names,
            max_concurrent_deployments=payload.max_concurrent_deployments,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    domain_event_service.record_event(
        event_type="operator.governance_updated",
        category="operator",
        severity="info",
        source="api.control_plane.update_governance",
        title="Strategy governance updated",
        message=f"Operator updated governance for {strategy_name}.",
        strategy_name=strategy_name,
        actor_type="operator",
        actor_id="api",
        payload_json={
            "approval_state": record.approval_state,
            "autonomous_operation_allowed": record.autonomous_operation_allowed,
            "emergency_stop": record.emergency_stop,
            "approved_asset_classes": record.approved_asset_classes,
            "approved_instruments": record.approved_instruments,
            "approved_profile_names": record.approved_profile_names,
        },
    )
    return {
        "strategy_name": record.strategy_name,
        "approval_state": record.approval_state,
        "autonomous_operation_allowed": record.autonomous_operation_allowed,
        "emergency_stop": record.emergency_stop,
        "approved_asset_classes": record.approved_asset_classes,
        "approved_instruments": record.approved_instruments,
        "approved_profile_names": record.approved_profile_names,
        "updated_at": record.updated_at,
    }
