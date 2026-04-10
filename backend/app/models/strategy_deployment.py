from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrategyDeploymentState(str, Enum):
    NOT_APPROVED = "NOT_APPROVED"
    APPROVED = "APPROVED"
    AUTO_DEPLOYABLE = "AUTO_DEPLOYABLE"
    AUTO_DEPLOYED = "AUTO_DEPLOYED"
    AUTO_PAUSED = "AUTO_PAUSED"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    EMERGENCY_STOPPED = "EMERGENCY_STOPPED"


class StrategyDeployment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    strategy_name: str = Field(index=True)
    governance_id: int | None = Field(default=None, index=True)
    deployment_key: str = Field(index=True, unique=True)
    state: str = Field(default=StrategyDeploymentState.NOT_APPROVED.value, index=True)
    selected_profile: str | None = None
    selected_instrument: str | None = Field(default=None, index=True)
    selected_asset_class: str | None = Field(default=None, index=True)
    control_mode: str = Field(default="AUTO", index=True)
    suitability_score: float | None = None
    suitability_reason: str | None = None
    selected_profile_parameters: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    profile_selected_at: datetime | None = None
    profile_change_reason: str | None = None
    blocked_reason: str | None = None
    degraded_reason: str | None = None
    last_restart_reason: str | None = None
    last_evaluated_at: datetime | None = None
    last_state_changed_at: datetime = Field(default_factory=utc_now, nullable=False)
    last_deployed_at: datetime | None = None
    operator_intervention_state: str | None = None
    deployment_metadata: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)
