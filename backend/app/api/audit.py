from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlmodel import Session

from app.services.domain_event_service import domain_event_service


def persist_required_domain_event(
    *,
    session: Session,
    failure_detail: str,
    event_type: str,
    category: str,
    source: str,
    title: str,
    severity: str = "info",
    error_type: str | None = None,
    message: str | None = None,
    correlation_id: str | None = None,
    runtime_id: str | None = None,
    strategy_name: str | None = None,
    instrument: str | None = None,
    position_id: int | None = None,
    trade_id: int | None = None,
    execution_id: int | None = None,
    actor_type: str | None = None,
    actor_id: str | None = None,
    payload_json: dict[str, Any] | None = None,
) -> None:
    event = domain_event_service.record_event_in_session(
        session=session,
        event_type=event_type,
        category=category,
        severity=severity,
        error_type=error_type,
        source=source,
        title=title,
        message=message,
        correlation_id=correlation_id,
        runtime_id=runtime_id,
        strategy_name=strategy_name,
        instrument=instrument,
        position_id=position_id,
        trade_id=trade_id,
        execution_id=execution_id,
        actor_type=actor_type,
        actor_id=actor_id,
        payload_json=payload_json,
    )
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=failure_detail,
        )
