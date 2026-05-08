from __future__ import annotations

from app.api.routes.executions import _serialize_execution
from app.models.trade import Execution, ExecutionPhase, ExecutionStatus


def test_audit_life_001_execution_response_preserves_ambiguity_and_correlation(
    fixed_now,
):
    execution = Execution(
        id=7,
        trade_intent_id=3,
        strategy_name="smoke_test_hold",
        instrument="CS.D.EURUSD.MINI.IP",
        phase=ExecutionPhase.ENTRY.value,
        status=ExecutionStatus.NEEDS_MANUAL_REVIEW.value,
        client_request_id="ent-ambiguous-route-1",
        broker_reference="entry-ambiguous-route-1",
        local_position_id=11,
        signal_time=fixed_now,
        requested_size=0.2,
        requested_price=100.0,
        requires_manual_review=True,
        reason="Broker result is not final; manual review required.",
        error_code="BROKER_CONFIRMATION_AMBIGUOUS",
        details={
            "broker_result": {
                "status": "AMBIGUOUS",
                "client_request_id": "ent-ambiguous-route-1",
                "broker_reference": "entry-ambiguous-route-1",
            },
            "reconciliation_linked_open_position": True,
            "reconciled_broker_reference": "entry-ambiguous-route-1",
        },
    )

    response = _serialize_execution(execution)

    assert response.status == ExecutionStatus.NEEDS_MANUAL_REVIEW.value
    assert response.requires_manual_review is True
    assert response.client_request_id == "ent-ambiguous-route-1"
    assert response.broker_reference == "entry-ambiguous-route-1"
    assert response.local_position_id == 11
    assert response.error_code == "BROKER_CONFIRMATION_AMBIGUOUS"
    assert response.details["broker_result"]["status"] == "AMBIGUOUS"
    assert response.details["broker_result"]["client_request_id"] == (
        "ent-ambiguous-route-1"
    )
    assert response.details["reconciliation_linked_open_position"] is True
