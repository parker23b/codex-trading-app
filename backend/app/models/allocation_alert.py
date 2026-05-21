from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, Index, text
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AllocationAlert(SQLModel, table=True):
    __table_args__ = (
        Index("ix_allocationalert_updated_at_desc", text("updated_at DESC")),
        Index(
            "ix_allocationalert_state_updated_at",
            "state",
            text("updated_at DESC"),
        ),
        Index(
            "ix_allocationalert_severity_updated_at",
            "severity",
            text("updated_at DESC"),
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    alert_key: str = Field(index=True, unique=True)
    alert_type: str = Field(index=True)
    severity: str = Field(default="warning", index=True)
    state: str = Field(default="OPEN", index=True)
    escalation_level: str = Field(default="none", index=True)
    title: str
    message: str | None = None
    count: int = 0
    recurrence_count: int = 1
    first_seen_at: datetime = Field(default_factory=utc_now, index=True)
    last_seen_at: datetime = Field(default_factory=utc_now, index=True)
    last_evaluated_at: datetime = Field(default_factory=utc_now, index=True)
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    escalated_at: datetime | None = None
    related_intent_ids: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    related_cycle_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    related_execution_ids: list[int] = Field(
        default_factory=list, sa_column=Column(JSON)
    )
    details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False, index=True)
