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


def test_audit_risk_002_execution_response_surfaces_material_risk_drift(
    fixed_now,
):
    risk_reconciliation = {
        "submitted": {
            "risk_amount": 20.0,
            "size": 0.2,
            "risk_truth_confidence": "SUBMITTED_EXECUTABLE_ESTIMATE",
        },
        "filled": {
            "risk_amount": 30.0,
            "size": 0.2,
            "risk_truth_confidence": "BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED",
        },
        "drift_metrics": {
            "submitted_to_fill_risk": {
                "expected": 20.0,
                "actual": 30.0,
                "percent_drift_abs": 50.0,
                "material": True,
            }
        },
        "flags": {
            "material_execution_drift": True,
            "critical_execution_drift": True,
        },
    }
    execution = Execution(
        id=8,
        trade_intent_id=4,
        strategy_name="smoke_test_hold",
        instrument="CS.D.EURUSD.MINI.IP",
        phase=ExecutionPhase.ENTRY.value,
        status=ExecutionStatus.POSITION_OPENED.value,
        client_request_id="ent-fill-drift-route-1",
        broker_reference="entry-fill-drift-route-1",
        signal_time=fixed_now,
        requested_size=0.2,
        filled_size=0.2,
        requested_price=100.0,
        average_fill_price=120.0,
        intended_risk_amount=20.0,
        submitted_risk_amount=20.0,
        fill_derived_risk_amount=30.0,
        risk_truth_confidence="BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED",
        details={"risk_reconciliation": risk_reconciliation},
    )

    response = _serialize_execution(execution)

    assert response.submitted_risk_amount == 20.0
    assert response.fill_derived_risk_amount == 30.0
    assert response.material_execution_drift is True
    assert response.critical_execution_drift is True
    assert response.risk_reconciliation == risk_reconciliation
    assert (
        response.risk_reconciliation["drift_metrics"]["submitted_to_fill_risk"][
            "material"
        ]
        is True
    )
