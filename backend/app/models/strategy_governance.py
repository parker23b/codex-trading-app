from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GovernanceApprovalState(str, Enum):
    NOT_APPROVED = "NOT_APPROVED"
    APPROVED = "APPROVED"
    DISABLED = "DISABLED"


class StrategyFamilyGovernance(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    strategy_name: str = Field(index=True, unique=True)
    approval_state: str = Field(
        default=GovernanceApprovalState.NOT_APPROVED.value, index=True
    )
    autonomous_operation_allowed: bool = False
    emergency_stop: bool = False
    approved_asset_classes: list[str] = Field(
        default_factory=list, sa_column=Column(JSON)
    )
    approved_instruments: list[str] = Field(
        default_factory=list, sa_column=Column(JSON)
    )
    approved_profile_names: list[str] = Field(
        default_factory=list, sa_column=Column(JSON)
    )
    max_concurrent_deployments: int = 1
    notes: str | None = None
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)
