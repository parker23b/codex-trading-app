from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from app.core.broker import OrderDirection
from app.models.trade import Position


class SignalKind(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


class SignalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"


@dataclass(slots=True)
class EntrySignal:
    kind: SignalKind
    strategy_name: str
    instrument: str
    observed_price: float
    signal_at: datetime
    direction: OrderDirection
    size: float
    risk_percent: float
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    expected_reward_risk: float | None = None
    volatility_estimate: float | None = None
    thesis: str | None = None
    strategy_metadata: dict[str, Any] = field(default_factory=dict)
    bid: float | None = None
    ask: float | None = None
    market_status: str | None = None
    tradable: bool | None = None
    status: SignalStatus = SignalStatus.PENDING
    reason: str | None = None
    rejection_layer: str | None = None
    audit_trail: list[dict[str, object]] = field(default_factory=list)
    audit_summary: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class ExitSignal:
    kind: SignalKind
    strategy_name: str
    instrument: str
    observed_price: float
    signal_at: datetime
    position: Position | None
    bid: float | None = None
    ask: float | None = None
    market_status: str | None = None
    tradable: bool | None = None
    status: SignalStatus = SignalStatus.PENDING
    reason: str | None = None


@dataclass(slots=True)
class SignalCandidate:
    strategy_name: str
    instrument: str
    signal: EntrySignal | ExitSignal | None
    engine: Any
    source_tier: str = "TIER1"
    confidence: float | None = None
    metadata: Any | None = None


@dataclass(slots=True)
class TradeAllocationDecision:
    candidate: SignalCandidate
    selected: bool
    reason_code: str
    reason: str
    score: float | None = None
