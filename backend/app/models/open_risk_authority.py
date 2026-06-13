from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OpenRiskAuthority(SQLModel, table=True):
    """Versioned authority for open-risk ownership in the active risk book."""

    id: Optional[int] = Field(default=None, primary_key=True)
    scope_key: str = Field(default="primary", unique=True, index=True)
    version: int = Field(default=1, nullable=False)
    state: str = Field(default="NO_OPEN_RISK", index=True)
    reason: str | None = None
    open_position_count: int = Field(default=0, nullable=False)
    reconciliation_status: str = Field(default="UNKNOWN", index=True)
    last_reconciled_at: datetime | None = None
    snapshot_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)
