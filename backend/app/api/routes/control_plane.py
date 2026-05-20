from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.api.audit import persist_required_domain_event
from app.api.auth import build_operator_audit_context, resolve_request_settings
from app.api.contracts.control_plane import (
    ControlPlaneFamilyResponse,
    ControlPlaneReconcileResponse,
    ControlPlaneSummaryResponse,
    GovernanceMutationResponse,
    OperatorControlResponse,
)
from app.api.errors import operator_error_detail
from app.db.session import get_session
from app.models.strategy_governance import GovernanceApprovalState
from app.services.control_plane_service import ControlPlaneService
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
    request: Request,
    session: Session = Depends(get_session),
) -> OperatorControlResponse:
    operator_context = build_operator_audit_context(
        request, settings=resolve_request_settings(request)
    )
    state = OperatorControlService(session).update_autonomous_control(
        enabled=payload.autonomous_control_enabled,
        reason=payload.reason,
    )
    persist_required_domain_event(
        session=session,
        failure_detail=(
            "Operator control was updated, but durable audit persistence failed."
        ),
        event_type="operator.autonomy_override_updated",
        category="operator",
        severity="info",
        source="api.control_plane.update_operator_state",
        title="Autonomous control override updated",
        message="Operator updated the global autonomous control override.",
        correlation_id=operator_context["correlation_id"],
        actor_type=str(operator_context["actor_type"]),
        actor_id=str(operator_context["actor_id"]),
        payload_json={
            "autonomous_control_override": state.autonomous_control_override,
            "override_reason": state.override_reason,
        },
    )
    return OperatorControlResponse(**OperatorControlService(session).get_summary())


@router.get(
    "/control-plane/strategies/{strategy_name}",
    response_model=ControlPlaneFamilyResponse,
)
def get_control_plane_strategy_detail(
    strategy_name: str,
    session: Session = Depends(get_session),
) -> ControlPlaneFamilyResponse:
    try:
        return ControlPlaneFamilyResponse(
            **ControlPlaneService(session).get_family_detail(strategy_name)
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=operator_error_detail(
                exc,
                default_detail=f"Strategy '{strategy_name}' was not found.",
            ),
        ) from exc


@router.post("/control-plane/reconcile", response_model=ControlPlaneReconcileResponse)
def reconcile_control_plane(
    request: Request,
    session: Session = Depends(get_session),
) -> ControlPlaneReconcileResponse:
    operator_context = build_operator_audit_context(
        request, settings=resolve_request_settings(request)
    )
    result = StrategyDeploymentManagerService(session).reconcile(
        startup_context={
            "authority_kind": "http_route",
            "route_source": "api.control_plane.reconcile",
            "route_path": request.url.path,
            "actor_type": operator_context["actor_type"],
            "actor_id": operator_context["actor_id"],
            "correlation_id": operator_context["correlation_id"],
        }
    )
    persist_required_domain_event(
        session=session,
        failure_detail=(
            "Control plane reconciliation completed, but durable audit persistence failed."
        ),
        event_type="control_plane.reconciled",
        category="strategy",
        severity="info",
        source="api.control_plane.reconcile",
        title="Control plane reconciliation completed",
        message="Autonomous deployment manager completed a reconciliation cycle.",
        correlation_id=operator_context["correlation_id"],
        actor_type=str(operator_context["actor_type"]),
        actor_id=str(operator_context["actor_id"]),
        payload_json={
            "deployed": result.deployed,
            "paused": result.paused,
            "blocked": result.blocked,
            "degraded": result.degraded,
            "emergency_stopped": result.emergency_stopped,
            "startup_context": {
                "authority_kind": "http_route",
                "route_source": "api.control_plane.reconcile",
                "route_path": request.url.path,
                "actor_type": operator_context["actor_type"],
                "actor_id": operator_context["actor_id"],
                "correlation_id": operator_context["correlation_id"],
            },
        },
    )
    return ControlPlaneReconcileResponse(
        deployed=result.deployed,
        paused=result.paused,
        blocked=result.blocked,
        degraded=result.degraded,
        emergency_stopped=result.emergency_stopped,
    )


@router.put(
    "/control-plane/governance/{strategy_name}",
    response_model=GovernanceMutationResponse,
)
def update_strategy_governance(
    strategy_name: str,
    payload: GovernanceUpdateRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> GovernanceMutationResponse:
    operator_context = build_operator_audit_context(
        request, settings=resolve_request_settings(request)
    )
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
            status_code=status.HTTP_404_NOT_FOUND,
            detail=operator_error_detail(
                exc,
                default_detail=f"Strategy '{strategy_name}' was not found.",
            ),
        ) from exc
    persist_required_domain_event(
        session=session,
        failure_detail=(
            "Strategy governance was updated, but durable audit persistence failed."
        ),
        event_type="operator.governance_updated",
        category="operator",
        severity="info",
        source="api.control_plane.update_governance",
        title="Strategy governance updated",
        message=f"Operator updated governance for {strategy_name}.",
        strategy_name=strategy_name,
        correlation_id=operator_context["correlation_id"],
        actor_type=str(operator_context["actor_type"]),
        actor_id=str(operator_context["actor_id"]),
        payload_json={
            "approval_state": record.approval_state,
            "autonomous_operation_allowed": record.autonomous_operation_allowed,
            "emergency_stop": record.emergency_stop,
            "approved_asset_classes": record.approved_asset_classes,
            "approved_instruments": record.approved_instruments,
            "approved_profile_names": record.approved_profile_names,
        },
    )
    return GovernanceMutationResponse(
        strategy_name=record.strategy_name,
        approval_state=record.approval_state,
        autonomous_operation_allowed=record.autonomous_operation_allowed,
        emergency_stop=record.emergency_stop,
        approved_asset_classes=record.approved_asset_classes,
        approved_instruments=record.approved_instruments,
        approved_profile_names=record.approved_profile_names,
        max_concurrent_deployments=record.max_concurrent_deployments,
        notes=record.notes,
        updated_at=record.updated_at,
    )
