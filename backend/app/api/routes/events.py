from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.models.domain_event import DomainEvent
from app.services.domain_event_service import domain_event_service

router = APIRouter()


class DomainEventResponse(BaseModel):
    id: int
    created_at: datetime
    event_type: str
    category: str
    severity: str
    source: str
    correlation_id: str | None
    runtime_id: str | None
    strategy_name: str | None
    instrument: str | None
    position_id: int | None
    trade_id: int | None
    execution_id: int | None
    actor_type: str | None
    actor_id: str | None
    title: str
    message: str | None
    payload_json: dict[str, object]


def _serialize_event(event: DomainEvent) -> DomainEventResponse:
    return DomainEventResponse(
        id=event.id or 0,
        created_at=event.created_at,
        event_type=event.event_type,
        category=event.category,
        severity=event.severity,
        source=event.source,
        correlation_id=event.correlation_id,
        runtime_id=event.runtime_id,
        strategy_name=event.strategy_name,
        instrument=event.instrument,
        position_id=event.position_id,
        trade_id=event.trade_id,
        execution_id=event.execution_id,
        actor_type=event.actor_type,
        actor_id=event.actor_id,
        title=event.title,
        message=event.message,
        payload_json=event.payload_json,
    )


@router.get("/events", response_model=list[DomainEventResponse])
def list_events(
    limit: int = Query(default=100, ge=1, le=500),
    event_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    strategy_name: str | None = Query(default=None),
    instrument: str | None = Query(default=None),
    correlation_id: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
) -> list[DomainEventResponse]:
    events = domain_event_service.list_events(
        limit=limit,
        event_type=event_type,
        category=category,
        severity=severity,
        strategy_name=strategy_name,
        instrument=instrument,
        correlation_id=correlation_id,
        since=since,
        until=until,
    )
    return [_serialize_event(event) for event in events]


@router.get("/events/{event_id}", response_model=DomainEventResponse)
def get_event(event_id: int) -> DomainEventResponse:
    event = domain_event_service.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Event '{event_id}' not found.")
    return _serialize_event(event)
