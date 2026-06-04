from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime
from typing import Any
from collections.abc import Callable

from sqlmodel import Session, desc, select

from app.core.logging import get_logger
from app.core.redaction import sanitize_error_detail, sanitize_payload, sanitize_text
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
        error_type: str | None = None,
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
            error_type=error_type,
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
            title=sanitize_text(title) or title,
            message=sanitize_text(message),
            payload_json=sanitize_payload(payload_json or {}),
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

    def record_event_in_session(
        self,
        *,
        session: Session,
        event_type: str,
        category: str,
        severity: str = "info",
        error_type: str | None = None,
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
            error_type=error_type,
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
            title=sanitize_text(title) or title,
            message=sanitize_text(message),
            payload_json=sanitize_payload(payload_json or {}),
        )
        try:
            session.add(event)
            session.commit()
            session.refresh(event)
            return event
        except Exception:
            session.rollback()
            logger.exception(
                "Failed to persist domain event in active session",
                extra={
                    "event_type": event_type,
                    "category": category,
                    "severity": severity,
                    "source": source,
                    "correlation_id": correlation_id,
                },
            )
            return None

    def record_error(
        self,
        *,
        error_type: str,
        source: str,
        title: str,
        message: str | None = None,
        category: str = "health",
        event_type: str = "system.error",
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
        exc: BaseException | None = None,
    ) -> DomainEvent | None:
        payload = sanitize_payload(dict(payload_json or {}))
        payload.setdefault("error_type", error_type)
        if exc is not None:
            payload.setdefault(
                "exception_message",
                sanitize_error_detail(
                    exc,
                    default_detail="Internal error details redacted.",
                ),
            )
            payload.setdefault("traceback", "[TRACEBACK REDACTED]")
            payload.setdefault("exception_type", type(exc).__name__)
        return self.record_event(
            event_type=event_type,
            category=category,
            severity="error",
            error_type=error_type,
            source=source,
            title=title,
            message=message
            or (
                sanitize_error_detail(
                    exc,
                    default_detail="Internal error details redacted.",
                )
                if exc is not None
                else None
            ),
            correlation_id=correlation_id,
            runtime_id=runtime_id,
            strategy_name=strategy_name,
            instrument=instrument,
            position_id=position_id,
            trade_id=trade_id,
            execution_id=execution_id,
            actor_type=actor_type,
            actor_id=actor_id,
            payload_json=payload,
            created_at=created_at,
        )

    def list_events(
        self,
        *,
        session: Session | None = None,
        limit: int = 100,
        event_type: str | None = None,
        error_type: str | None = None,
        category: str | None = None,
        severity: str | None = None,
        strategy_name: str | None = None,
        instrument: str | None = None,
        correlation_id: str | None = None,
        correlation_filter: Callable[[str | None], bool] | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[DomainEvent]:
        with self._session_scope(session) as active_session:
            statement = select(DomainEvent)
            if event_type:
                statement = statement.where(DomainEvent.event_type == event_type)
            if error_type:
                statement = statement.where(DomainEvent.error_type == error_type)
            if category:
                statement = statement.where(DomainEvent.category == category)
            if severity:
                statement = statement.where(DomainEvent.severity == severity)
            if strategy_name:
                statement = statement.where(DomainEvent.strategy_name == strategy_name)
            if instrument:
                statement = statement.where(DomainEvent.instrument == instrument)
            if correlation_id:
                statement = statement.where(
                    DomainEvent.correlation_id == correlation_id
                )
            if since:
                statement = statement.where(DomainEvent.created_at >= since)
            if until:
                statement = statement.where(DomainEvent.created_at <= until)
            statement = statement.order_by(
                desc(DomainEvent.created_at), desc(DomainEvent.id)
            )
            events = list(active_session.exec(statement))
            if correlation_filter is not None:
                events = [
                    event
                    for event in events
                    if correlation_filter(event.correlation_id)
                ]
            return events[:limit]

    def get_event(
        self, event_id: int, *, session: Session | None = None
    ) -> DomainEvent | None:
        with self._session_scope(session) as active_session:
            statement = select(DomainEvent).where(DomainEvent.id == event_id)
            return active_session.exec(statement).first()

    def _session_scope(self, session: Session | None):
        if session is not None:
            return nullcontext(session)
        return Session(engine)


domain_event_service = DomainEventService()
