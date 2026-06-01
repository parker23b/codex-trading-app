from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.contracts.identifiers import IdentifierProjection


class DashboardBrokerInfoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accountId: IdentifierProjection
    accountType: Literal["DEMO", "LIVE"]
    balance: float
    available: float
    equity: float
    profitLoss: float


class DashboardRunningStrategyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    instrument: str
    runtimeKey: str
    brokerReference: IdentifierProjection | None = None
    instrumentLabel: str
    lastPrice: float | None = None
    hasOpenPosition: bool


class DashboardSnapshotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accountValue: float
    accountValuePercent: float | None = None
    dailyPnl: float
    dailyPnlPercent: float | None = None
    openRisk: float
    winRate: float
    riskReward: float
    brokerInfo: DashboardBrokerInfoResponse | None = None
    runningStrategies: list[DashboardRunningStrategyResponse] = Field(
        default_factory=list
    )
