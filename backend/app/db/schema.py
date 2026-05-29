from __future__ import annotations

from sqlmodel import SQLModel

from app.models.allocation_alert import AllocationAlert
from app.models.domain_event import DomainEvent
from app.models.observability import ObservabilityState
from app.models.operator_control import OperatorControlState
from app.models.promotion_request import PromotionRequest
from app.models.review import GeneratedReviewRecord
from app.models.runtime import StrategyRuntimeState
from app.models.runtime_leadership import RuntimeLease
from app.models.strategy_deployment import StrategyDeployment
from app.models.strategy_governance import StrategyFamilyGovernance
from app.models.trade import (
    AllocationCycle,
    Execution,
    Position,
    ReconciliationEvent,
    Trade,
    TradeIntent,
)
from app.models.watchlist import OperatorShortlistEntry, WatchlistEntry

MODEL_TYPES = (
    AllocationAlert,
    AllocationCycle,
    DomainEvent,
    Execution,
    GeneratedReviewRecord,
    ObservabilityState,
    OperatorControlState,
    OperatorShortlistEntry,
    Position,
    PromotionRequest,
    ReconciliationEvent,
    RuntimeLease,
    StrategyDeployment,
    StrategyFamilyGovernance,
    StrategyRuntimeState,
    Trade,
    TradeIntent,
    WatchlistEntry,
)


def load_sqlmodel_metadata():
    _ = MODEL_TYPES
    return SQLModel.metadata
