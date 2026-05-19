from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlmodel import select

from app.core.broker import (
    AccountType,
    BrokerAccountSummary,
    BrokerMarketDetails,
    BrokerSizingMode,
    OrderDirection,
)
from app.core.runtime import runtime_manager
from app.services.health_service import get_health_service
from app.core.signals import EntrySignal, SignalCandidate, SignalKind
from app.models.domain_event import DomainEvent
from app.models.trade import AllocationCycle, TradeIntent, TradeIntentState
from app.services.capital_allocator_service import CapitalAllocatorService
from app.services.domain_event_service import domain_event_service
from app.services.trade_decision_service import TradeDecisionService
from app.services.trade_service import TradeService


INSTRUMENT = "CS.D.EURUSD.CFD.IP"
STRATEGY = "mean_reversion"


def _events(session) -> list[DomainEvent]:
    return list(session.exec(select(DomainEvent).order_by(DomainEvent.id)))


def _allocation_cycles(session) -> list[AllocationCycle]:
    return list(session.exec(select(AllocationCycle).order_by(AllocationCycle.id)))


def _trade_intents(session) -> list[TradeIntent]:
    return list(session.exec(select(TradeIntent).order_by(TradeIntent.id)))


def _candidate(
    *,
    broker,
    fixed_now: datetime,
    instrument: str = INSTRUMENT,
    strategy_name: str = STRATEGY,
    risk_per_trade: float = 0.5,
    confidence: float = 0.8,
    stop_loss_price: float | None = 1.09,
    price: float = 1.1,
) -> SignalCandidate:
    broker.account_summary = BrokerAccountSummary(
        account_id="audit-demo",
        balance=100_000.0,
        available=100_000.0,
        profit_loss=0.0,
        equity=100_000.0,
        account_type=AccountType.DEMO,
    )
    broker.market_details_by_instrument.setdefault(
        instrument,
        BrokerMarketDetails(
            instrument=instrument,
            name=instrument,
            bid=price,
            offer=price,
            high=price + 0.01,
            low=price - 0.01,
            percentage_change=0.0,
            net_change=0.0,
            market_status="TRADEABLE",
            update_time=fixed_now.isoformat(),
            tradable=True,
            min_deal_size=0.01,
            size_step=0.01,
            base_currency="EUR",
            quote_currency="USD",
            metadata={
                "sizing_profile": {
                    "mode": BrokerSizingMode.APPROXIMATE_PRICE_DELTA.value,
                    "contract_multiplier": 1.0,
                }
            },
        ),
    )
    return SignalCandidate(
        strategy_name=strategy_name,
        instrument=instrument,
        signal=EntrySignal(
            kind=SignalKind.ENTRY,
            strategy_name=strategy_name,
            instrument=instrument,
            observed_price=price,
            signal_at=fixed_now,
            direction=OrderDirection.BUY,
            size=0.0,
            risk_percent=risk_per_trade,
            stop_loss_price=stop_loss_price,
            bid=price,
            ask=price,
            market_status="TRADEABLE",
            tradable=True,
        ),
        engine=SimpleNamespace(
            strategy=SimpleNamespace(name=strategy_name),
            broker=broker,
            instrument=instrument,
        ),
        source_tier="TIER1",
        confidence=confidence,
        metadata=SimpleNamespace(family_name=strategy_name),
    )


def _enable_live_entry_context(monkeypatch, fixed_now: datetime) -> None:
    now = datetime.now(UTC)
    health_service = get_health_service()
    health_service.update_broker_state(connected=True, latency_ms=5.0)
    health_service.record_price_update(now, stream_connected=True)
    stub = type(
        "StreamService",
        (),
        {
            "get_health": lambda self: type(
                "Health",
                (),
                {
                    "enabled": True,
                    "connected": True,
                    "subscribed_instruments": (),
                    "desired_instruments": (),
                    "last_tick_at": now,
                },
            )()
        },
    )()
    monkeypatch.setattr(
        "app.services.operational_state_service.get_operational_streaming_service",
        lambda: stub,
    )


def _seed_trade_intent(session, *, state: str = TradeIntentState.PROPOSED.value):
    return TradeService(session).create_trade_intent(
        TradeIntent(
            strategy_name=STRATEGY,
            family_name=STRATEGY,
            allocation_cycle_id="alloc-audit-seed",
            instrument=INSTRUMENT,
            direction="BUY",
            state=state,
            signal_time=datetime(2026, 4, 10, 9, 0, tzinfo=UTC),
            proposed_size=0.2,
            allocated_size=0.2,
            proposed_risk_percent=0.5,
            allocated_risk_percent=0.5,
            estimated_risk_amount=500.0,
            risk_truth_confidence="ALLOCATION_INTENT_ONLY",
            confidence=0.8,
            observed_price=1.1,
            market_status="TRADEABLE",
            tradable=True,
            decision_reason_code="proposed",
            decision_reason="Proposed for audit test.",
            details={
                "allocation_outcome": {
                    "stage": "proposed_for_risk_overlay",
                    "final_status": state,
                }
            },
        )
    )


def test_audit_test_002_allocation_cycle_persists_domain_event_despite_global_noop(
    session, broker, fixed_now
):
    decision = CapitalAllocatorService(session).allocate(
        [_candidate(broker=broker, fixed_now=fixed_now)],
        received_at=fixed_now,
    )[0]

    events = _events(session)
    cycles = _allocation_cycles(session)
    assert len(cycles) == 1
    assert len(events) == 1
    event = events[0]
    assert event.event_type == "allocation.cycle_completed"
    assert event.category == "allocation"
    assert event.source == "capital_allocator_service.allocate"
    assert event.actor_type == "service"
    assert event.actor_id == "capital_allocator_service"
    assert event.correlation_id == decision.cycle_id
    assert event.payload_json["cycle_id"] == decision.cycle_id
    assert event.payload_json["previous_state"] == "NOT_CREATED"
    assert event.payload_json["new_state"] == "COMPLETED"
    assert event.payload_json["candidate_count"] == 1
    assert event.payload_json["approved_count"] == 1
    assert event.payload_json["rejected_count"] == 0
    assert event.payload_json["decisions"] == [
        {
            "strategy_name": STRATEGY,
            "instrument": INSTRUMENT,
            "direction": "BUY",
            "selected": True,
            "reason_code": "allocated",
            "requested_risk_percent": pytest.approx(0.5),
            "allocated_risk_percent": pytest.approx(decision.allocated_risk_percent),
            "risk_truth_confidence": "ALLOCATION_INTENT_ONLY",
            "degraded": decision.degraded,
        }
    ]


def test_audit_obs_001_allocation_cycle_marks_audit_persistence_failure(
    session, broker, fixed_now, monkeypatch
):
    monkeypatch.setattr(
        domain_event_service,
        "record_event_in_session",
        lambda **_: None,
        raising=False,
    )

    decision = CapitalAllocatorService(session).allocate(
        [_candidate(broker=broker, fixed_now=fixed_now)],
        received_at=fixed_now,
    )[0]

    cycles = _allocation_cycles(session)
    assert len(cycles) == 1
    assert cycles[0].cycle_id == decision.cycle_id
    assert cycles[0].details["domain_event_persistence_failed"] is True
    assert cycles[0].details["audit_event_failures"] == [
        {
            "event_type": "allocation.cycle_completed",
            "source": "capital_allocator_service.allocate",
            "previous_state": "NOT_CREATED",
            "new_state": "COMPLETED",
            "correlation_id": decision.cycle_id,
        }
    ]
    assert _events(session) == []


def test_audit_test_002_trade_intent_creation_persists_domain_event(session):
    intent = _seed_trade_intent(session)

    events = _events(session)
    assert len(events) == 1
    event = events[0]
    assert event.event_type == "trade_intent.created"
    assert event.category == "decision"
    assert event.source == "trade_service.create_trade_intent"
    assert event.actor_type == "service"
    assert event.actor_id == "trade_service"
    assert event.correlation_id == f"trade_intent:{intent.id}"
    assert event.strategy_name == STRATEGY
    assert event.instrument == INSTRUMENT
    assert event.payload_json["trade_intent_id"] == intent.id
    assert event.payload_json["allocation_cycle_id"] == "alloc-audit-seed"
    assert event.payload_json["previous_state"] == "NOT_CREATED"
    assert event.payload_json["new_state"] == TradeIntentState.PROPOSED.value
    assert event.payload_json["decision_reason_code"] == "proposed"
    assert event.payload_json["risk_truth_confidence"] == "ALLOCATION_INTENT_ONLY"


def test_audit_test_002_trade_intent_transition_persists_domain_event(session):
    intent = _seed_trade_intent(session)

    updated = TradeService(session).transition_trade_intent(
        intent,
        state=TradeIntentState.APPROVED,
        decision_reason_code="approved",
        decision_reason="Approved by audit regression.",
        execution_client_request_id="entry-client-audit-1",
        risk_truth_confidence="ALLOCATION_INTENT_ONLY",
    )

    events = _events(session)
    assert updated.state == TradeIntentState.APPROVED.value
    assert [event.event_type for event in events] == [
        "trade_intent.created",
        "trade_intent.state_changed",
    ]
    event = events[1]
    assert event.category == "decision"
    assert event.source == "trade_service.transition_trade_intent"
    assert event.actor_type == "service"
    assert event.actor_id == "trade_service"
    assert event.correlation_id == "entry-client-audit-1"
    assert event.payload_json["trade_intent_id"] == intent.id
    assert event.payload_json["previous_state"] == TradeIntentState.PROPOSED.value
    assert event.payload_json["new_state"] == TradeIntentState.APPROVED.value
    assert event.payload_json["decision_reason_code"] == "approved"
    assert event.payload_json["decision_reason"] == "Approved by audit regression."


def test_audit_test_002_trade_intent_transition_records_related_domain_ids(session):
    intent = _seed_trade_intent(session)

    TradeService(session).transition_trade_intent(
        intent,
        state=TradeIntentState.CLOSED,
        position_id=17,
        trade_id=23,
        broker_reference="entry-ref-audit",
        close_broker_reference="close-ref-audit",
        execution_client_request_id="close-client-audit-1",
        close_reason_code="broker_close_confirmed",
        close_reason="Broker close confirmed.",
        risk_truth_confidence="BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED",
    )

    event = _events(session)[1]
    assert event.event_type == "trade_intent.state_changed"
    assert event.position_id == 17
    assert event.trade_id == 23
    assert event.correlation_id == "close-client-audit-1"
    assert event.payload_json["trade_intent_id"] == intent.id
    assert event.payload_json["previous_state"] == TradeIntentState.PROPOSED.value
    assert event.payload_json["new_state"] == TradeIntentState.CLOSED.value
    assert event.payload_json["broker_reference"] == "entry-ref-audit"
    assert event.payload_json["close_broker_reference"] == "close-ref-audit"
    assert event.payload_json["close_reason_code"] == "broker_close_confirmed"
    assert (
        event.payload_json["risk_truth_confidence"]
        == "BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED"
    )


def test_audit_obs_001_trade_intent_audit_failure_marks_intent(session, monkeypatch):
    intent = _seed_trade_intent(session)
    original_record_event_in_session = domain_event_service.record_event_in_session

    def fail_transition_event(**kwargs):
        if kwargs.get("event_type") == "trade_intent.state_changed":
            return None
        return original_record_event_in_session(**kwargs)

    monkeypatch.setattr(
        domain_event_service,
        "record_event_in_session",
        fail_transition_event,
        raising=False,
    )

    updated = TradeService(session).transition_trade_intent(
        intent,
        state=TradeIntentState.REJECTED,
        decision_reason_code="risk_rejected",
        decision_reason="Rejected by audit regression.",
    )

    assert updated.state == TradeIntentState.REJECTED.value
    assert updated.details["domain_event_persistence_failed"] is True
    assert updated.details["audit_event_failures"] == [
        {
            "event_type": "trade_intent.state_changed",
            "source": "trade_service.transition_trade_intent",
            "previous_state": TradeIntentState.PROPOSED.value,
            "new_state": TradeIntentState.REJECTED.value,
            "correlation_id": f"trade_intent:{intent.id}",
        }
    ]
    assert [event.event_type for event in _events(session)] == ["trade_intent.created"]


def test_audit_test_002_decision_flow_links_allocation_and_intent_audit_events(
    session, broker, fixed_now, monkeypatch
):
    now = datetime.now(UTC)
    _enable_live_entry_context(monkeypatch, now)
    runtime_manager.last_price_updated_at[INSTRUMENT] = now
    result = TradeDecisionService(session).decide_signal_candidates(
        [_candidate(broker=broker, fixed_now=now)],
        received_at=now,
    )[0]

    events = _events(session)
    intents = _trade_intents(session)
    cycles = _allocation_cycles(session)
    assert result.admitted is True
    assert len(intents) == 1
    assert len(cycles) == 1
    assert [event.event_type for event in events] == [
        "allocation.cycle_completed",
        "trade_intent.created",
        "trade_intent.state_changed",
    ]
    assert events[0].correlation_id == cycles[0].cycle_id
    assert events[1].correlation_id == f"trade_intent:{intents[0].id}"
    assert events[2].correlation_id == f"trade_intent:{intents[0].id}"
    assert events[1].payload_json["allocation_cycle_id"] == cycles[0].cycle_id
    assert events[2].payload_json["allocation_cycle_id"] == cycles[0].cycle_id
    assert events[1].payload_json["previous_state"] == "NOT_CREATED"
    assert events[1].payload_json["new_state"] == TradeIntentState.PROPOSED.value
    assert events[2].payload_json["previous_state"] == TradeIntentState.PROPOSED.value
    assert events[2].payload_json["new_state"] == TradeIntentState.APPROVED.value
    assert events[2].payload_json["decision_reason_code"] == "approved"


def test_audit_test_002_rejected_decision_flow_persists_rejection_audit_event(
    session, broker, fixed_now
):
    result = TradeDecisionService(session).decide_signal_candidates(
        [
            _candidate(
                broker=broker,
                fixed_now=fixed_now,
                risk_per_trade=0.5,
                stop_loss_price=None,
            )
        ],
        received_at=fixed_now,
    )[0]

    events = _events(session)
    intents = _trade_intents(session)
    assert result.admitted is False
    assert len(intents) == 1
    assert [event.event_type for event in events] == [
        "allocation.cycle_completed",
        "trade_intent.created",
        "trade_intent.state_changed",
    ]
    assert events[1].payload_json["trade_intent_id"] == intents[0].id
    assert events[1].payload_json["previous_state"] == "NOT_CREATED"
    assert events[1].payload_json["new_state"] == TradeIntentState.PROPOSED.value
    assert events[2].payload_json["trade_intent_id"] == intents[0].id
    assert events[2].payload_json["previous_state"] == TradeIntentState.PROPOSED.value
    assert events[2].payload_json["new_state"] == TradeIntentState.REJECTED.value
    assert events[2].payload_json["decision_reason_code"] == (
        "operational_policy_blocked"
    )
    assert events[1].payload_json["allocation_cycle_id"] == events[0].correlation_id
    assert events[2].payload_json["allocation_cycle_id"] == events[0].correlation_id
