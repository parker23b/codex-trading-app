from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, Index, text
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DomainEvent(SQLModel, table=True):
    __tablename__ = "domain_events"
    __table_args__ = (
        Index("ix_domain_events_created_at_desc", text("created_at DESC")),
        Index(
            "ix_domain_events_category_created_at",
            "category",
            text("created_at DESC"),
        ),
        Index(
            "ix_domain_events_strategy_created_at",
            "strategy_name",
            text("created_at DESC"),
        ),
        Index(
            "ix_domain_events_instrument_created_at",
            "instrument",
            text("created_at DESC"),
        ),
        Index(
            "ix_domain_events_severity_created_at",
            "severity",
            text("created_at DESC"),
        ),
        Index(
            "ix_domain_events_correlation_created_at",
            "correlation_id",
            text("created_at DESC"),
        ),
        Index(
            "ix_domain_events_error_type_created_at",
            "error_type",
            text("created_at DESC"),
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utc_now, nullable=False, index=True)
    event_type: str = Field(index=True)
    category: str = Field(index=True)
    severity: str = Field(default="info", index=True)
    error_type: str | None = Field(default=None, index=True)
    source: str = Field(index=True)
    correlation_id: str | None = Field(default=None, index=True)
    runtime_id: str | None = Field(default=None, index=True)
    strategy_name: str | None = Field(default=None, index=True)
    instrument: str | None = Field(default=None, index=True)
    position_id: int | None = Field(default=None, index=True)
    trade_id: int | None = Field(default=None, index=True)
    execution_id: int | None = Field(default=None, index=True)
    actor_type: str | None = Field(default=None, index=True)
    actor_id: str | None = Field(default=None, index=True)
    title: str
    message: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
