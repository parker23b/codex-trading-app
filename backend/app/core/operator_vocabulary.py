from __future__ import annotations

from app.core.broker import BrokerExecutionSource
from app.core.risk_truth import RiskTruthConfidence
from app.models.trade import (
    BrokerSyncStatus,
    ExecutionStatus,
    TradeIntentState,
)

RISK_TRUTH_CONFIDENCE_VALUES = tuple(
    confidence.value for confidence in RiskTruthConfidence
)
BROKER_EXECUTION_SOURCE_VALUES = tuple(source.value for source in BrokerExecutionSource)
BROKER_SYNC_STATUS_VALUES = tuple(status.value for status in BrokerSyncStatus)
EXECUTION_STATUS_VALUES = tuple(status.value for status in ExecutionStatus)
TRADE_INTENT_STATE_VALUES = tuple(state.value for state in TradeIntentState)
