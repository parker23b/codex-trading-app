from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, Index, UniqueConstraint, text
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ObservabilityState(SQLModel, table=True):
    __tablename__ = "observabilitystate"
    __table_args__ = (
        UniqueConstraint(
            "state_key",
            "scope_type",
            "scope_id",
            "worker_id",
            name="uq_observabilitystate_key_scope_worker",
        ),
        Index(
            "ix_observabilitystate_key_updated_desc",
            "state_key",
            text("observed_at DESC"),
        ),
        Index(
            "ix_observabilitystate_scope_updated_desc",
            "scope_type",
            "scope_id",
            text("observed_at DESC"),
        ),
        Index(
            "ix_observabilitystate_worker_updated_desc",
            "worker_id",
            text("observed_at DESC"),
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    state_key: str = Field(index=True)
    scope_type: str = Field(default="SYSTEM", index=True)
    scope_id: str = Field(default="global", index=True)
    worker_id: str = Field(index=True)
    hostname: str = Field(index=True)
    process_id: int = Field(index=True)
    source: str = Field(index=True)
    status: str = Field(default="ACTIVE", index=True)
    observed_at: datetime = Field(default_factory=utc_now, nullable=False, index=True)
    expires_at: datetime | None = Field(default=None, index=True)
    payload_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
