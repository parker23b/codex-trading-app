from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlmodel import select

from app.core.identifier_policy import project_identifier
from app.models.allocation_alert import AllocationAlert
from app.models.trade import (
    AllocationCycle,
    Execution,
    Position,
    Trade,
    TradeIntent,
    TradeIntentState,
)


INSTRUMENT = "CS.D.EURUSD.CFD.IP"


def _seed_allocation_contract_state(session) -> dict[str, int | str]:
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    cycle = AllocationCycle(
        cycle_id="cycle-contract-1",
        received_at=now,
        completed_at=now + timedelta(seconds=2),
        candidate_count=2,
        approved_count=1,
        rejected_count=1,
        total_requested_risk_percent=0.9,
        total_allocated_risk_percent=0.5,
        remaining_portfolio_risk_percent=3.5,
        resized_candidate_count=1,
        degraded_candidate_count=1,
        blocked_unsupported_sizing_count=0,
        blocked_approximate_live_count=0,
        blocked_under_minimum_size_count=0,
        blocked_budget_count=1,
        blocked_conflict_count=0,
        binding_budget_counts={"portfolio": 1},
        rejection_reason_counts={"budget_blocked": 1},
        details={"degraded": True, "route_contract": "allocation"},
    )
    session.add(cycle)
    session.commit()

    intent = TradeIntent(
        strategy_name="mean_reversion",
        family_name="fx",
        allocation_cycle_id=cycle.cycle_id,
        instrument=INSTRUMENT,
        direction="BUY",
        state=TradeIntentState.PARTIALLY_FILLED.value,
        signal_time=now,
        proposed_size=1.2,
        allocated_size=1.0,
        proposed_risk_percent=0.6,
        allocated_risk_percent=0.5,
        estimated_risk_amount=60.0,
        submitted_risk_amount=50.0,
        fill_derived_risk_amount=25.0,
        risk_truth_confidence="PARTIAL_FILL_PROVISIONAL",
        risk_currency="USD",
        confidence=0.82,
        decision_reason_code="approved",
        decision_reason="Approved with residual risk still open.",
        observed_price=1.1,
        average_fill_price=1.101,
        filled_size=0.5,
        broker_reference="deal-contract-1",
        execution_client_request_id="entry-contract-1",
        submitted_at=now + timedelta(seconds=1),
        acknowledged_at=now + timedelta(seconds=1),
        opened_at=now + timedelta(seconds=2),
        updated_at=now + timedelta(seconds=3),
        details={
            "allocation": {
                "binding_budget": "portfolio",
                "broker_details": {"base_currency": "EUR", "quote_currency": "USD"},
            },
            "allocation_outcome": {
                "stage": "partially_filled",
                "fill_status": TradeIntentState.PARTIALLY_FILLED.value,
            },
            "risk_tracking": {"risk_state": "partial_fill"},
            "risk_reconciliation": {
                "flags": {
                    "partial_fill_provisional": True,
                    "incomplete_fill_data": False,
                    "material_execution_drift": True,
                },
                "drift_metrics": {
                    "submitted_to_fill_risk": {
                        "percent_drift_abs": 50.0,
                        "material": True,
                    }
                },
                "filled": {
                    "risk_amount": 25.0,
                    "risk_truth_confidence": "PARTIAL_FILL_PROVISIONAL",
                },
            },
            "partial_fill": {"submitted_size": 1.0, "residual_size": 0.5},
        },
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)

    execution = Execution(
        trade_intent_id=intent.id,
        strategy_name=intent.strategy_name,
        instrument=intent.instrument,
        phase="ENTRY",
        status="FILL_PARTIAL",
        client_request_id="entry-contract-1",
        broker_reference="deal-contract-1",
        signal_time=now,
        submitted_at=now + timedelta(seconds=1),
        acknowledged_at=now + timedelta(seconds=1),
        completed_at=now + timedelta(seconds=2),
        requested_size=1.0,
        filled_size=0.5,
        requested_price=1.1,
        average_fill_price=1.101,
        intended_risk_amount=60.0,
        submitted_risk_amount=50.0,
        fill_derived_risk_amount=25.0,
        risk_truth_confidence="PARTIAL_FILL_PROVISIONAL",
        reason="Partial fill kept residual reserved risk active.",
        requires_manual_review=True,
        details={
            "risk_reconciliation": {
                "flags": {
                    "material_execution_drift": True,
                    "critical_execution_drift": False,
                }
            }
        },
        created_at=now + timedelta(seconds=1),
        updated_at=now + timedelta(seconds=2),
    )
    session.add(execution)
    session.commit()
    session.refresh(execution)

    position = Position(
        trade_intent_id=intent.id,
        strategy_name=intent.strategy_name,
        family_name=intent.family_name,
        broker_reference="deal-contract-1",
        instrument=intent.instrument,
        direction="BUY",
        size=0.5,
        open_price=1.101,
        open_time=now + timedelta(seconds=2),
        current_price=1.102,
        unrealized_pnl=5.0,
        risk_percent=0.25,
        entry_risk_amount=25.0,
        risk_truth_confidence="PARTIAL_FILL_PROVISIONAL",
        account_type="DEMO",
        is_open=True,
    )
    session.add(position)
    session.commit()
    session.refresh(position)

    trade = Trade(
        trade_intent_id=intent.id,
        strategy_name=intent.strategy_name,
        family_name=intent.family_name,
        broker_reference="deal-contract-1",
        close_broker_reference=None,
        instrument=intent.instrument,
        direction="BUY",
        size=0.5,
        open_price=1.101,
        close_price=1.101,
        open_time=now + timedelta(seconds=2),
        close_time=now + timedelta(seconds=2),
        pnl=0.0,
        entry_risk_amount=25.0,
        risk_truth_confidence="PARTIAL_FILL_PROVISIONAL",
        account_type="DEMO",
        reason="Still open; trade record exists for parity coverage.",
    )
    session.add(trade)
    session.commit()
    session.refresh(trade)

    intent.position_id = position.id
    intent.trade_id = trade.id
    session.add(intent)
    session.commit()

    return {"cycle_id": cycle.cycle_id, "trade_intent_id": int(intent.id or 0)}


def _seed_alert(
    session,
    *,
    alert_key: str,
    severity: str,
    state: str = "OPEN",
    now: datetime | None = None,
) -> AllocationAlert:
    timestamp = now or datetime(2026, 5, 1, 12, 30, tzinfo=UTC)
    alert = AllocationAlert(
        alert_key=alert_key,
        alert_type="material_execution_drift",
        severity=severity,
        state=state,
        escalation_level="critical" if severity == "error" else "warning",
        title="Material execution drift",
        message="Risk truth drift needs operator attention.",
        count=2,
        recurrence_count=3,
        first_seen_at=timestamp - timedelta(minutes=10),
        last_seen_at=timestamp,
        acknowledged_at=timestamp if state != "OPEN" else None,
        resolved_at=timestamp if state == "RESOLVED" else None,
        related_intent_ids=[7],
        related_cycle_ids=["cycle-contract-1"],
        related_execution_ids=[42],
        details={"source": "route-contract"},
    )
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return alert


def test_allocation_contract_routes_expose_nested_risk_truth_and_drift(
    session, client_factory
):
    seeded = _seed_allocation_contract_state(session)

    with client_factory() as client:
        cycles_response = client.get("/allocation/cycles")
        assert cycles_response.status_code == 200
        cycles = cycles_response.json()
        assert cycles[0]["cycle_id"] == seeded["cycle_id"]
        assert cycles[0]["details"]["route_contract"] == "allocation"

        cycle_detail_response = client.get(f"/allocation/cycles/{seeded['cycle_id']}")
        assert cycle_detail_response.status_code == 200
        cycle_detail = cycle_detail_response.json()
        assert cycle_detail["intents"][0]["id"] == seeded["trade_intent_id"]
        assert (
            cycle_detail["intents"][0]["risk_truth_confidence"]
            == "PARTIAL_FILL_PROVISIONAL"
        )

        intent_response = client.get(f"/allocation/intents/{seeded['trade_intent_id']}")
        assert intent_response.status_code == 200
        intent = intent_response.json()
        assert intent["risk_truth_confidence"] == "PARTIAL_FILL_PROVISIONAL"
        assert (
            intent["latest_execution"]["risk_truth_confidence"]
            == "PARTIAL_FILL_PROVISIONAL"
        )
        assert intent["position"]["risk_truth_confidence"] == "PARTIAL_FILL_PROVISIONAL"
        assert intent["trade"]["risk_truth_confidence"] == "PARTIAL_FILL_PROVISIONAL"
        assert (
            intent["risk_reconciliation"]["flags"]["partial_fill_provisional"] is True
        )
        assert (
            intent["risk_reconciliation"]["drift_metrics"]["submitted_to_fill_risk"][
                "percent_drift_abs"
            ]
            == 50.0
        )
        assert intent["latest_execution"]["client_request_id"] == project_identifier(
            "entry-contract-1",
            kind="request_id",
        )
        assert intent["latest_execution"]["broker_reference"] == project_identifier(
            "deal-contract-1",
            kind="broker_reference",
        )
        assert intent["position"]["broker_reference"] == project_identifier(
            "deal-contract-1",
            kind="broker_reference",
        )
        assert intent["trade"]["broker_reference"] == project_identifier(
            "deal-contract-1",
            kind="broker_reference",
        )

        drift_response = client.get("/allocation/drift")
        assert drift_response.status_code == 200
        drift = drift_response.json()
        assert drift["material_drift_count"] == 1
        assert drift["worst_intents"][0]["trade_intent_id"] == seeded["trade_intent_id"]
        assert (
            drift["worst_intents"][0]["drift_metrics"]["submitted_to_fill_risk"][
                "percent_drift_abs"
            ]
            == 50.0
        )


def test_allocation_alert_routes_share_full_frontend_contract_and_typed_mutations(
    session, client_factory
):
    open_alert = _seed_alert(session, alert_key="alert-open", severity="error")
    _seed_alert(
        session, alert_key="alert-resolved", severity="warning", state="RESOLVED"
    )

    with client_factory() as client:
        alerts_response = client.get("/allocation/alerts?include_resolved=true")
        assert alerts_response.status_code == 200
        alerts = alerts_response.json()
        assert alerts[0]["severity"] in {"error", "warning"}
        assert "escalation_level" in alerts[0]
        assert "first_seen_at" in alerts[0]
        assert "last_seen_at" in alerts[0]
        assert "related_intent_ids" in alerts[0]
        assert "related_cycle_ids" in alerts[0]
        assert "related_execution_ids" in alerts[0]

        unresolved_response = client.get("/allocation/alerts/unresolved-critical")
        assert unresolved_response.status_code == 200
        unresolved = unresolved_response.json()
        assert len(unresolved) == 1
        assert unresolved[0]["id"] == open_alert.id
        assert unresolved[0]["severity"] == "error"
        assert unresolved[0]["escalation_level"] == "critical"
        assert unresolved[0]["first_seen_at"] is not None
        assert unresolved[0]["acknowledged_at"] is None
        assert unresolved[0]["resolved_at"] is None

        acknowledged_response = client.post(
            f"/allocation/alerts/{open_alert.id}/acknowledge",
            json={"actor_id": "route-contract"},
        )
        assert acknowledged_response.status_code == 200
        acknowledged = acknowledged_response.json()
        assert set(acknowledged.keys()) == {
            "id",
            "state",
            "acknowledged_at",
            "resolved_at",
        }
        assert acknowledged["state"] == "ACKNOWLEDGED"
        assert acknowledged["acknowledged_at"] is not None
        assert acknowledged["resolved_at"] is None

        resolved_response = client.post(
            f"/allocation/alerts/{open_alert.id}/resolve",
            json={"actor_id": "route-contract"},
        )
        assert resolved_response.status_code == 200
        resolved = resolved_response.json()
        assert set(resolved.keys()) == {"id", "state", "acknowledged_at", "resolved_at"}
        assert resolved["state"] == "RESOLVED"
        assert resolved["resolved_at"] is not None

        persisted = session.exec(select(AllocationAlert)).all()
        assert any(alert.state == "RESOLVED" for alert in persisted)


def test_allocation_exposure_route_preserves_provisional_risk_and_basis_notes(
    session, client_factory
):
    _seed_allocation_contract_state(session)

    with client_factory() as client:
        response = client.get("/allocation/exposure")
        assert response.status_code == 200
        payload = response.json()

    assert payload["totals"]["reserved_risk_percent"] == 0.25
    assert payload["totals"]["live_risk_percent"] == 0.25
    assert payload["totals"]["provisional_live_risk_percent"] == 0.25
    assert payload["totals"]["remaining_portfolio_risk_percent"] >= 0.0
    assert any(
        bucket["name"] == INSTRUMENT and "partial_fill_residual" in bucket["risk_basis"]
        for bucket in payload["by_instrument"]
    )
    assert payload["notes"]["reserved_risk_basis"]
    assert payload["notes"]["live_risk_basis"]
