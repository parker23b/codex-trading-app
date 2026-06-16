from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.api.contracts.allocation import (
    AllocationAlertMutationResponse,
    AllocationAlertResponse,
    AllocationCycleResponse,
    AllocationDriftSummaryResponse,
    AllocationExposureSummaryResponse,
    AllocationIntentResponse,
)
from app.api.audit import persist_required_domain_event
from app.api.auth import build_operator_audit_context, resolve_request_settings
from app.db.session import get_session
from app.models.allocation_alert import AllocationAlert
from app.services.allocation_alert_service import AllocationAlertService
from app.services.allocation_read_service import AllocationReadService

router = APIRouter(prefix="/allocation")


class AlertActionRequest(BaseModel):
    # Deprecated compatibility field. HTTP attribution is server-derived.
    actor_id: str = Field(default="operator")


def _persist_alert_mutation_event(
    *,
    session: Session,
    alert: AllocationAlert,
    action: str,
    previous_state: str,
    actor_id: str,
) -> None:
    event_action = "acknowledged" if action == "acknowledge" else "resolved"
    persist_required_domain_event(
        session=session,
        failure_detail=(
            f"Allocation alert was {event_action}, but durable audit persistence failed."
        ),
        event_type=f"operator.allocation_alert_{event_action}",
        category="risk",
        source=f"api.allocation.alerts.{action}",
        title=f"Allocation alert {event_action}",
        message=alert.title,
        actor_type="operator",
        actor_id=actor_id,
        payload_json={
            "alert_id": alert.id,
            "alert_key": alert.alert_key,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "previous_state": previous_state,
            "state": alert.state,
            "related_intent_ids": alert.related_intent_ids,
            "related_cycle_ids": alert.related_cycle_ids,
            "related_execution_ids": alert.related_execution_ids,
        },
    )


@router.get("/cycles", response_model=list[AllocationCycleResponse])
def list_allocation_cycles(
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[AllocationCycleResponse]:
    return [
        AllocationCycleResponse.model_validate(cycle)
        for cycle in AllocationReadService(session).list_recent_cycles(limit=limit)
    ]


@router.get("/cycles/{cycle_id}", response_model=AllocationCycleResponse)
def get_allocation_cycle(
    cycle_id: str,
    session: Session = Depends(get_session),
) -> AllocationCycleResponse:
    cycle = AllocationReadService(session).get_cycle(cycle_id)
    if cycle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Allocation cycle '{cycle_id}' not found.",
        )
    return AllocationCycleResponse.model_validate(cycle)


@router.get("/intents", response_model=list[AllocationIntentResponse])
def list_allocation_intents(
    limit: int = Query(default=100, ge=1, le=500),
    cycle_id: str | None = Query(default=None),
    strategy_name: str | None = Query(default=None),
    instrument: str | None = Query(default=None),
    state: list[str] | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[AllocationIntentResponse]:
    return [
        AllocationIntentResponse.model_validate(intent)
        for intent in AllocationReadService(session).list_intents(
            limit=limit,
            cycle_id=cycle_id,
            strategy_name=strategy_name,
            instrument=instrument,
            states=state,
        )
    ]


@router.get("/intents/{trade_intent_id}", response_model=AllocationIntentResponse)
def get_allocation_intent(
    trade_intent_id: int,
    session: Session = Depends(get_session),
) -> AllocationIntentResponse:
    intent = AllocationReadService(session).get_intent(trade_intent_id)
    if intent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trade intent '{trade_intent_id}' not found.",
        )
    return AllocationIntentResponse.model_validate(intent)


@router.get("/drift", response_model=AllocationDriftSummaryResponse)
def get_allocation_drift_summary(
    limit: int = Query(default=100, ge=1, le=500),
    window_minutes: int | None = Query(default=None, ge=1, le=10_080),
    session: Session = Depends(get_session),
) -> AllocationDriftSummaryResponse:
    return AllocationDriftSummaryResponse.model_validate(
        AllocationReadService(session).get_drift_summary(
            limit=limit, window_minutes=window_minutes
        )
    )


@router.get("/alerts", response_model=list[AllocationAlertResponse])
def list_allocation_alerts(
    limit: int = Query(default=50, ge=1, le=500),
    window_minutes: int | None = Query(default=None, ge=1, le=10_080),
    include_resolved: bool = Query(default=False),
    refresh: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> list[AllocationAlertResponse]:
    alerts = AllocationAlertService(session).list_alerts(
        limit=limit,
        include_resolved=include_resolved,
        refresh=refresh,
        window_minutes=window_minutes,
    )
    return [
        AllocationAlertResponse.model_validate(
            {
                "id": alert.id,
                "alert_key": alert.alert_key,
                "alert_type": alert.alert_type,
                "severity": alert.severity,
                "state": alert.state,
                "escalation_level": alert.escalation_level,
                "title": alert.title,
                "message": alert.message,
                "count": alert.count,
                "recurrence_count": alert.recurrence_count,
                "first_seen_at": alert.first_seen_at,
                "last_seen_at": alert.last_seen_at,
                "acknowledged_at": alert.acknowledged_at,
                "resolved_at": alert.resolved_at,
                "related_intent_ids": alert.related_intent_ids,
                "related_cycle_ids": alert.related_cycle_ids,
                "related_execution_ids": alert.related_execution_ids,
                "details": alert.details,
            }
        )
        for alert in alerts
    ]


@router.post(
    "/alerts/{alert_id}/acknowledge",
    response_model=AllocationAlertMutationResponse,
)
def acknowledge_allocation_alert(
    alert_id: int,
    payload: AlertActionRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> AllocationAlertMutationResponse:
    operator_context = build_operator_audit_context(
        request, settings=resolve_request_settings(request)
    )
    actor_id = str(operator_context["actor_id"])
    existing = AllocationAlertService(session).trade_service.get_allocation_alert(
        alert_id
    )
    previous_state = existing.state if existing is not None else None
    alert = AllocationAlertService(session).acknowledge_alert(
        alert_id, actor_id=actor_id
    )
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Allocation alert '{alert_id}' not found.",
        )
    _persist_alert_mutation_event(
        session=session,
        alert=alert,
        action="acknowledge",
        previous_state=previous_state or "UNKNOWN",
        actor_id=actor_id,
    )
    return AllocationAlertMutationResponse.model_validate(
        {
            "id": alert.id,
            "state": alert.state,
            "acknowledged_at": alert.acknowledged_at,
        }
    )


@router.post(
    "/alerts/{alert_id}/resolve", response_model=AllocationAlertMutationResponse
)
def resolve_allocation_alert(
    alert_id: int,
    payload: AlertActionRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> AllocationAlertMutationResponse:
    operator_context = build_operator_audit_context(
        request, settings=resolve_request_settings(request)
    )
    actor_id = str(operator_context["actor_id"])
    existing = AllocationAlertService(session).trade_service.get_allocation_alert(
        alert_id
    )
    previous_state = existing.state if existing is not None else None
    alert = AllocationAlertService(session).resolve_alert(alert_id, actor_id=actor_id)
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Allocation alert '{alert_id}' not found.",
        )
    _persist_alert_mutation_event(
        session=session,
        alert=alert,
        action="resolve",
        previous_state=previous_state or "UNKNOWN",
        actor_id=actor_id,
    )
    return AllocationAlertMutationResponse.model_validate(
        {"id": alert.id, "state": alert.state, "resolved_at": alert.resolved_at}
    )


@router.get("/alerts/unresolved-critical", response_model=list[AllocationAlertResponse])
def list_unresolved_critical_allocation_alerts(
    limit: int = Query(default=50, ge=1, le=500),
    window_minutes: int | None = Query(default=None, ge=1, le=10_080),
    session: Session = Depends(get_session),
) -> list[AllocationAlertResponse]:
    alerts = AllocationAlertService(session).list_alerts(
        limit=limit,
        include_resolved=False,
        refresh=False,
        window_minutes=window_minutes,
    )
    critical = [alert for alert in alerts if alert.severity == "error"]
    return [
        AllocationAlertResponse.model_validate(
            {
                "id": alert.id,
                "alert_key": alert.alert_key,
                "alert_type": alert.alert_type,
                "severity": alert.severity,
                "state": alert.state,
                "escalation_level": alert.escalation_level,
                "title": alert.title,
                "message": alert.message,
                "count": alert.count,
                "recurrence_count": alert.recurrence_count,
                "first_seen_at": alert.first_seen_at,
                "last_seen_at": alert.last_seen_at,
                "acknowledged_at": alert.acknowledged_at,
                "resolved_at": alert.resolved_at,
                "related_intent_ids": alert.related_intent_ids,
                "related_cycle_ids": alert.related_cycle_ids,
                "related_execution_ids": alert.related_execution_ids,
                "details": alert.details,
            }
        )
        for alert in critical
    ]


@router.get("/exposure", response_model=AllocationExposureSummaryResponse)
def get_allocation_exposure_summary(
    session: Session = Depends(get_session),
) -> AllocationExposureSummaryResponse:
    return AllocationExposureSummaryResponse.model_validate(
        AllocationReadService(session).get_exposure_summary()
    )
