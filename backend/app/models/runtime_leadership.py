from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RuntimeLease(SQLModel, table=True):
    __table_args__ = (
        Index("ix_runtimelease_owner_expires", "owner_id", text("expires_at DESC")),
    )

    lease_name: str = Field(primary_key=True)
    owner_id: str = Field(index=True)
    generation: int = Field(default=1, nullable=False)
    acquired_at: datetime = Field(default_factory=utc_now, nullable=False)
    heartbeat_at: datetime = Field(default_factory=utc_now, nullable=False)
    expires_at: datetime = Field(index=True, nullable=False)
    released_at: datetime | None = Field(default=None, index=True)
