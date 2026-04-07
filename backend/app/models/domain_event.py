from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DomainEvent(SQLModel, table=True):
    __tablename__ = "domain_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utc_now, nullable=False, index=True)
    event_type: str = Field(index=True)
    category: str = Field(index=True)
    severity: str = Field(default="info", index=True)
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
