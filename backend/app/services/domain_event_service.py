from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlmodel import Session, desc, select

from app.core.logging import get_logger
from app.db.session import engine
from app.models.domain_event import DomainEvent, utc_now

logger = get_logger(__name__)


class DomainEventService:
    """Append-only operational event journal."""

    def record_event(
        self,
        *,
        event_type: str,
        category: str,
        severity: str = "info",
        source: str,
        title: str,
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
        created_at: datetime | None = None,
    ) -> DomainEvent | None:
        event = DomainEvent(
            created_at=created_at or utc_now(),
            event_type=event_type,
            category=category,
            severity=severity,
            source=source,
            correlation_id=correlation_id,
            runtime_id=runtime_id,
            strategy_name=strategy_name,
            instrument=instrument,
            position_id=position_id,
            trade_id=trade_id,
            execution_id=execution_id,
            actor_type=actor_type,
            actor_id=actor_id,
            title=title,
            message=message,
            payload_json=payload_json or {},
        )
        try:
            with Session(engine) as session:
                session.add(event)
                session.commit()
                session.refresh(event)
                return event
        except Exception:
            logger.exception(
                "Failed to persist domain event",
                extra={
                    "event_type": event_type,
                    "category": category,
                    "severity": severity,
                    "source": source,
                    "correlation_id": correlation_id,
                },
            )
            return None

    def list_events(
        self,
        *,
        limit: int = 100,
        event_type: str | None = None,
        category: str | None = None,
        severity: str | None = None,
        strategy_name: str | None = None,
        instrument: str | None = None,
        correlation_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[DomainEvent]:
        with Session(engine) as session:
            statement = select(DomainEvent)
            if event_type:
                statement = statement.where(DomainEvent.event_type == event_type)
            if category:
                statement = statement.where(DomainEvent.category == category)
            if severity:
                statement = statement.where(DomainEvent.severity == severity)
            if strategy_name:
                statement = statement.where(DomainEvent.strategy_name == strategy_name)
            if instrument:
                statement = statement.where(DomainEvent.instrument == instrument)
            if correlation_id:
                statement = statement.where(DomainEvent.correlation_id == correlation_id)
            if since:
                statement = statement.where(DomainEvent.created_at >= since)
            if until:
                statement = statement.where(DomainEvent.created_at <= until)
            statement = statement.order_by(desc(DomainEvent.created_at), desc(DomainEvent.id)).limit(limit)
            return list(session.exec(statement))

    def get_event(self, event_id: int) -> DomainEvent | None:
        with Session(engine) as session:
            statement = select(DomainEvent).where(DomainEvent.id == event_id)
            return session.exec(statement).first()


domain_event_service = DomainEventService()
