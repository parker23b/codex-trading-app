from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrategyRuntimeState(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    runtime_id: str = Field(index=True, unique=True)
    strategy_name: str = Field(index=True)
    strategy_version: str = Field(default="1")
    instrument: str = Field(index=True)
    parameters: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    status: str = Field(default="STOPPED", index=True)
    recovery_state: str = Field(default="PENDING", index=True)
    recovery_reason: str | None = None
    started_at: datetime = Field(default_factory=utc_now, nullable=False)
    stopped_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    last_price_seen: float | None = None
    last_price_seen_at: datetime | None = None
    current_position_broker_reference: str | None = Field(default=None, index=True)
    control_mode: str = Field(default="MANUAL", index=True)
    deployment_id: int | None = Field(default=None, index=True)
    active_profile_name: str | None = Field(default=None, index=True)
    auto_resume: bool = True
    strategy_state_snapshot: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)
