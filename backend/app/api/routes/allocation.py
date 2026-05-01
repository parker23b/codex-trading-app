from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.db.session import get_session
from app.services.allocation_alert_service import AllocationAlertService
from app.services.allocation_read_service import AllocationReadService

router = APIRouter(prefix="/allocation")


class AlertActionRequest(BaseModel):
    actor_id: str = Field(default="operator")


@router.get("/cycles")
def list_allocation_cycles(
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    return AllocationReadService(session).list_recent_cycles(limit=limit)


@router.get("/cycles/{cycle_id}")
def get_allocation_cycle(
    cycle_id: str,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    cycle = AllocationReadService(session).get_cycle(cycle_id)
    if cycle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Allocation cycle '{cycle_id}' not found.",
        )
    return cycle


@router.get("/intents")
def list_allocation_intents(
    limit: int = Query(default=100, ge=1, le=500),
    cycle_id: str | None = Query(default=None),
    strategy_name: str | None = Query(default=None),
    instrument: str | None = Query(default=None),
    state: list[str] | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    return AllocationReadService(session).list_intents(
        limit=limit,
        cycle_id=cycle_id,
        strategy_name=strategy_name,
        instrument=instrument,
        states=state,
    )


@router.get("/intents/{trade_intent_id}")
def get_allocation_intent(
    trade_intent_id: int,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    intent = AllocationReadService(session).get_intent(trade_intent_id)
    if intent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trade intent '{trade_intent_id}' not found.",
        )
    return intent


@router.get("/drift")
def get_allocation_drift_summary(
    limit: int = Query(default=100, ge=1, le=500),
    window_minutes: int | None = Query(default=None, ge=1, le=10_080),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    return AllocationReadService(session).get_drift_summary(
        limit=limit, window_minutes=window_minutes
    )


@router.get("/alerts")
def list_allocation_alerts(
    limit: int = Query(default=50, ge=1, le=500),
    window_minutes: int | None = Query(default=None, ge=1, le=10_080),
    include_resolved: bool = Query(default=False),
    refresh: bool = Query(default=True),
    session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    alerts = AllocationAlertService(session).list_alerts(
        limit=limit,
        include_resolved=include_resolved,
        refresh=refresh,
        window_minutes=window_minutes,
    )
    return [
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
        for alert in alerts
    ]


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_allocation_alert(
    alert_id: int,
    payload: AlertActionRequest,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    alert = AllocationAlertService(session).acknowledge_alert(
        alert_id, actor_id=payload.actor_id
    )
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Allocation alert '{alert_id}' not found.",
        )
    return {
        "id": alert.id,
        "state": alert.state,
        "acknowledged_at": alert.acknowledged_at,
    }


@router.post("/alerts/{alert_id}/resolve")
def resolve_allocation_alert(
    alert_id: int,
    payload: AlertActionRequest,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    alert = AllocationAlertService(session).resolve_alert(
        alert_id, actor_id=payload.actor_id
    )
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Allocation alert '{alert_id}' not found.",
        )
    return {"id": alert.id, "state": alert.state, "resolved_at": alert.resolved_at}


@router.get("/alerts/unresolved-critical")
def list_unresolved_critical_allocation_alerts(
    limit: int = Query(default=50, ge=1, le=500),
    window_minutes: int | None = Query(default=None, ge=1, le=10_080),
    session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    alerts = AllocationAlertService(session).list_alerts(
        limit=limit, include_resolved=False, refresh=True, window_minutes=window_minutes
    )
    critical = [alert for alert in alerts if alert.severity == "error"]
    return [
        {
            "id": alert.id,
            "alert_key": alert.alert_key,
            "alert_type": alert.alert_type,
            "state": alert.state,
            "title": alert.title,
            "message": alert.message,
            "count": alert.count,
            "recurrence_count": alert.recurrence_count,
            "last_seen_at": alert.last_seen_at,
            "related_intent_ids": alert.related_intent_ids,
            "related_cycle_ids": alert.related_cycle_ids,
            "related_execution_ids": alert.related_execution_ids,
            "details": alert.details,
        }
        for alert in critical
    ]


@router.get("/exposure")
def get_allocation_exposure_summary(
    session: Session = Depends(get_session),
) -> dict[str, object]:
    return AllocationReadService(session).get_exposure_summary()
