from app.core.operator_vocabulary import (
    BROKER_EXECUTION_SOURCE_VALUES,
    BROKER_SYNC_STATUS_VALUES,
    EXECUTION_STATUS_VALUES,
    RISK_TRUTH_CONFIDENCE_VALUES,
    TRADE_INTENT_STATE_VALUES,
)
from app.core.broker import BrokerExecutionSource
from app.core.risk_truth import RiskTruthConfidence
from app.models.trade import BrokerSyncStatus, ExecutionStatus, TradeIntentState


def test_audit_005_operator_vocabulary_module_exports_authoritative_backend_values():
    assert RISK_TRUTH_CONFIDENCE_VALUES == tuple(
        confidence.value for confidence in RiskTruthConfidence
    )
    assert BROKER_EXECUTION_SOURCE_VALUES == tuple(
        source.value for source in BrokerExecutionSource
    )
    assert BROKER_SYNC_STATUS_VALUES == tuple(
        status.value for status in BrokerSyncStatus
    )
    assert EXECUTION_STATUS_VALUES == tuple(status.value for status in ExecutionStatus)
    assert TRADE_INTENT_STATE_VALUES == tuple(state.value for state in TradeIntentState)


def test_broker_014_broker_sync_status_includes_simulated_and_unknown_provenance():
    assert BrokerSyncStatus.SIMULATED_LOCAL_FILL.value in BROKER_SYNC_STATUS_VALUES
    assert BrokerSyncStatus.SIMULATED_LOCAL_CLOSE.value in BROKER_SYNC_STATUS_VALUES
    assert BrokerSyncStatus.UNKNOWN.value in BROKER_SYNC_STATUS_VALUES
    assert BrokerSyncStatus.UNAVAILABLE.value in BROKER_SYNC_STATUS_VALUES
