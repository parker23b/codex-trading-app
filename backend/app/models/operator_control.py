from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OperatorControlState(SQLModel, table=True):
    id: Optional[int] = Field(default=1, primary_key=True)
    autonomous_control_override: bool | None = Field(default=None, index=True)
    override_reason: str | None = None
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)
