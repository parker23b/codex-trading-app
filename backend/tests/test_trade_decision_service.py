from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from app.core.broker import AccountType, BrokerAccountSummary, BrokerMarketDetails, OrderDirection
from app.core.runtime import runtime_manager
from app.core.signals import EntrySignal, ExitSignal, SignalCandidate, SignalKind
from app.models.trade import TradeIntent, TradeIntentState
from app.services.health_service import get_health_service
from app.services.strategy_service import StrategyService
from app.services.trade_decision_service import TradeDecisionService
from app.services.trade_service import ActiveTradeIntentConflictError, TradeService
from tests.fakes import make_order_result


INSTRUMENT = "CS.D.EURUSD.MINI.IP"


def _candidate(
    *,
    strategy_name: str,
    instrument: str,
    direction: OrderDirection,
    signal_at,
    confidence: float,
    broker,
    price: float = 1.1001,
    market_status: str = "TRADEABLE",
    tradable: bool = True,
    position_size: float = 0.5,
    risk_per_trade: float = 0.4,
) -> SignalCandidate:
    signal = EntrySignal(
        kind=SignalKind.ENTRY,
        strategy_name=strategy_name,
        instrument=instrument,
        observed_price=price,
        signal_at=signal_at,
        direction=direction,
        size=position_size,
        risk_percent=risk_per_trade,
        bid=price - 0.0001,
        ask=price + 0.0001,
        market_status=market_status,
        tradable=tradable,
    )
    return SignalCandidate(
        strategy_name=strategy_name,
        instrument=instrument,
        signal=signal,
        engine=SimpleNamespace(strategy=SimpleNamespace(name=strategy_name), broker=broker, instrument=instrument),
        source_tier="TIER1",
        confidence=confidence,
        metadata=SimpleNamespace(position_size=position_size),
    )


def _enable_live_entry_context(monkeypatch) -> None:
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
    monkeypatch.setattr("app.services.operational_state_service.get_operational_streaming_service", lambda: stub)


def test_decision_service_persists_proposed_signal_as_approved_trade_intent(session, broker, fixed_now, monkeypatch):
    _enable_live_entry_context(monkeypatch)
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    decision_service = TradeDecisionService(session)
    candidate = _candidate(
        strategy_name="smoke_test_hold",
        instrument=INSTRUMENT,
        direction=OrderDirection.BUY,
        signal_at=fixed_now,
        confidence=0.9,
        broker=broker,
        position_size=0.2,
        risk_per_trade=0.1,
    )

    results = decision_service.decide_signal_candidates([candidate], received_at=fixed_now)
    intents = TradeService(session).list_trade_intents()

    assert len(results) == 1
    assert results[0].admitted is True
    assert results[0].intent is not None
    assert results[0].intent.state == TradeIntentState.APPROVED.value
    assert results[0].intent.allocated_size > 0
    assert results[0].intent.allocated_risk_percent == 0.1
    assert ((results[0].intent.details or {}).get("allocation") or {}).get("sizing_method") is not None
    assert intents[0].decision_reason_code == "approved"


def test_decision_service_resolves_same_instrument_competition_explicitly(session, broker, fixed_now, monkeypatch):
    _enable_live_entry_context(monkeypatch)
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    decision_service = TradeDecisionService(session)
    strong_buy = _candidate(
        strategy_name="breakout_guard",
        instrument=INSTRUMENT,
        direction=OrderDirection.BUY,
        signal_at=fixed_now,
        confidence=0.95,
        broker=broker,
    )
    conflicting_sell = _candidate(
        strategy_name="mean_reversion",
        instrument=INSTRUMENT,
        direction=OrderDirection.SELL,
        signal_at=fixed_now,
        confidence=0.45,
        broker=broker,
    )

    results = decision_service.decide_signal_candidates([conflicting_sell, strong_buy], received_at=fixed_now)
    by_strategy = {result.candidate.strategy_name: result for result in results}

    assert by_strategy["breakout_guard"].admitted is True
    assert by_strategy["breakout_guard"].intent.state == TradeIntentState.APPROVED.value
    assert by_strategy["mean_reversion"].admitted is False
    assert by_strategy["mean_reversion"].intent.state == TradeIntentState.REJECTED.value
    assert by_strategy["mean_reversion"].reason_code == "opposing_signal_blocked"


def test_decision_service_rejects_and_persists_below_min_size_reason(session, broker, fixed_now):
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    broker.account_summary = BrokerAccountSummary(
        account_id="tiny-risk",
        balance=1.1001,
        available=1.1001,
        profit_loss=0.0,
        equity=1.1001,
        account_type=AccountType.DEMO,
    )
    broker.market_details_by_instrument[INSTRUMENT] = BrokerMarketDetails(
        instrument=INSTRUMENT,
        name=INSTRUMENT,
        bid=1.1000,
        offer=1.1001,
        high=1.1010,
        low=1.0990,
        percentage_change=0.0,
        net_change=0.0,
        market_status="TRADEABLE",
        update_time=fixed_now.isoformat(),
        tradable=True,
        min_deal_size=1.0,
    )
    decision_service = TradeDecisionService(session)
    candidate = _candidate(
        strategy_name="smoke_test_hold",
        instrument=INSTRUMENT,
        direction=OrderDirection.BUY,
        signal_at=fixed_now,
        confidence=0.9,
        broker=broker,
        position_size=0.2,
        risk_per_trade=0.1,
    )

    result = decision_service.decide_signal_candidates([candidate], received_at=fixed_now)[0]

    assert result.admitted is False
    assert result.intent is not None
    assert result.intent.state == TradeIntentState.REJECTED.value
    assert result.reason_code == "below_min_size"
    assert result.intent.decision_reason_code == "below_min_size"


def test_decision_service_rejects_instrument_when_active_intent_exists(session, broker, fixed_now):
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    trade_service = TradeService(session)
    trade_service.create_trade_intent(
        TradeIntent(
            strategy_name="existing_strategy",
            instrument=INSTRUMENT,
            direction="BUY",
            state=TradeIntentState.POSITION_OPENED.value,
            signal_time=fixed_now - timedelta(minutes=2),
            proposed_size=0.5,
            allocated_size=0.5,
            proposed_risk_percent=0.4,
            allocated_risk_percent=0.4,
            decision_reason_code="approved",
            decision_reason="Existing live trade intent.",
        )
    )
    candidate = _candidate(
        strategy_name="challenger",
        instrument=INSTRUMENT,
        direction=OrderDirection.SELL,
        signal_at=fixed_now,
        confidence=0.8,
        broker=broker,
    )

    result = TradeDecisionService(session).decide_signal_candidates([candidate], received_at=fixed_now)[0]

    assert result.admitted is False
    assert result.reason_code == "instrument_already_allocated"
    assert result.intent.state == TradeIntentState.REJECTED.value


def test_only_approved_trade_intents_reach_order_submission(session, broker, fixed_now, monkeypatch):
    _enable_live_entry_context(monkeypatch)
    service = StrategyService(session)
    trade_service = TradeService(session)
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    broker.account_summary = BrokerAccountSummary(
        account_id="tiny-smoke",
        balance=101.0,
        available=101.0,
        profit_loss=0.0,
        equity=101.0,
        account_type=AccountType.DEMO,
    )
    candidate = _candidate(
        strategy_name="smoke_test_hold",
        instrument=INSTRUMENT,
        direction=OrderDirection.BUY,
        signal_at=fixed_now,
        confidence=0.9,
        broker=broker,
        market_status="CLOSED",
        tradable=False,
    )

    rejected_results = service.decide_signal_candidates([candidate], received_at=fixed_now)
    service.orchestrate_trade_decisions(rejected_results, price=1.1001, bid=1.1000, ask=1.1002, received_at=fixed_now)

    assert broker.placed_orders == []
    assert trade_service.list_executions(limit=10) == []
    assert trade_service.list_trade_intents(limit=10)[0].state == TradeIntentState.REJECTED.value

    service.start_strategy("smoke_test_hold", INSTRUMENT)
    broker.place_order_outcomes.append(
        make_order_result(
            broker_reference="approved-entry-1",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=101.0,
            average_fill_price=101.0,
            executed_at=fixed_now + timedelta(seconds=1),
        )
    )

    service.process_price_update(INSTRUMENT, 100.0, bid=99.99, ask=100.01, market_status="TRADEABLE", tradable=True, received_at=fixed_now)
    service.process_price_update(INSTRUMENT, 101.0, bid=100.99, ask=101.01, market_status="TRADEABLE", tradable=True, received_at=fixed_now + timedelta(seconds=1))

    assert len(broker.placed_orders) == 1


def test_same_instrument_candidates_do_not_leave_multiple_active_proposals(session, broker, fixed_now, monkeypatch):
    _enable_live_entry_context(monkeypatch)
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    decision_service = TradeDecisionService(session)
    first = _candidate(
        strategy_name="breakout_guard",
        instrument=INSTRUMENT,
        direction=OrderDirection.BUY,
        signal_at=fixed_now,
        confidence=0.95,
        broker=broker,
    )
    second = _candidate(
        strategy_name="carry_drift",
        instrument=INSTRUMENT,
        direction=OrderDirection.SELL,
        signal_at=fixed_now,
        confidence=0.7,
        broker=broker,
    )

    decision_service.decide_signal_candidates([first, second], received_at=fixed_now)
    intents = TradeService(session).list_trade_intents(limit=10)
    active_states = {TradeIntentState.PROPOSED.value, TradeIntentState.APPROVED.value}
    active = [intent for intent in intents if intent.state in active_states]

    assert len(active) == 1
    assert len([intent for intent in intents if intent.state == TradeIntentState.REJECTED.value]) == 1


def test_active_trade_intent_uniqueness_is_enforced_in_persistence(session, fixed_now):
    trade_service = TradeService(session)
    trade_service.create_trade_intent(
        TradeIntent(
            strategy_name="owner_one",
            instrument=INSTRUMENT,
            direction="BUY",
            state=TradeIntentState.APPROVED.value,
            signal_time=fixed_now,
            proposed_size=0.5,
            allocated_size=0.5,
            proposed_risk_percent=0.4,
            allocated_risk_percent=0.4,
            decision_reason_code="approved",
            decision_reason="Primary instrument owner.",
        )
    )

    with pytest.raises(ActiveTradeIntentConflictError):
        trade_service.create_trade_intent(
            TradeIntent(
                strategy_name="owner_two",
                instrument=INSTRUMENT,
                direction="SELL",
                state=TradeIntentState.PROPOSED.value,
                signal_time=fixed_now + timedelta(seconds=1),
                proposed_size=0.3,
                allocated_size=0.3,
                proposed_risk_percent=0.2,
                allocated_risk_percent=0.2,
                decision_reason_code="proposed",
                decision_reason="Competing owner should be blocked.",
            )
        )


def test_exit_candidate_is_rejected_without_linked_trade_intent(session, broker, fixed_now):
    service = StrategyService(session)
    exit_candidate = SignalCandidate(
        strategy_name="smoke_test_hold",
        instrument=INSTRUMENT,
        signal=ExitSignal(
            kind=SignalKind.EXIT,
            strategy_name="smoke_test_hold",
            instrument=INSTRUMENT,
            observed_price=1.1001,
            signal_at=fixed_now,
            position=SimpleNamespace(id=1, broker_reference="missing-intent-pos", size=0.2),
            bid=1.1,
            ask=1.1002,
            market_status="TRADEABLE",
            tradable=True,
        ),
        engine=SimpleNamespace(
            strategy=SimpleNamespace(name="smoke_test_hold"),
            broker=broker,
            instrument=INSTRUMENT,
            current_position=SimpleNamespace(
                broker_reference="missing-intent-pos",
                direction="BUY",
                open_price=1.0,
                size=0.2,
                strategy_name="smoke_test_hold",
                account_type="DEMO",
            ),
        ),
        source_tier="TIER1",
        metadata=SimpleNamespace(risk_per_trade=0.1),
    )

    decisions = service.decide_signal_candidates([exit_candidate], received_at=fixed_now)
    service.orchestrate_trade_decisions(decisions, price=1.1001, bid=1.1, ask=1.1002, received_at=fixed_now)

    assert decisions[0].admitted is False
    assert decisions[0].reason_code == "missing_open_trade_intent"
    assert broker.close_requests == []


def test_fallback_operational_policy_blocks_new_autonomous_entry(session, broker, monkeypatch):
    now = datetime.now(UTC)
    runtime_manager.last_price_updated_at[INSTRUMENT] = now
    health_service = get_health_service()
    health_service.update_broker_state(connected=True, latency_ms=5.0)
    health_service.record_price_update(now)
    stub = type(
        "StreamService",
        (),
        {
            "get_health": lambda self: type(
                "Health",
                (),
                {
                    "enabled": True,
                    "connected": False,
                    "subscribed_instruments": (),
                    "desired_instruments": (),
                    "last_tick_at": now - timedelta(seconds=30),
                },
            )()
        },
    )()
    monkeypatch.setattr("app.services.operational_state_service.get_operational_streaming_service", lambda: stub)
    candidate = _candidate(
        strategy_name="smoke_test_hold",
        instrument=INSTRUMENT,
        direction=OrderDirection.BUY,
        signal_at=now,
        confidence=0.9,
        broker=broker,
        position_size=0.2,
        risk_per_trade=0.1,
    )

    result = TradeDecisionService(session).decide_signal_candidates([candidate], received_at=now)[0]

    assert result.admitted is False
    assert result.reason_code == "operational_policy_blocked"
    assert result.intent is not None
    assert result.intent.state == TradeIntentState.REJECTED.value
    assert result.intent.decision_reason_code == "operational_policy_blocked"
    assert ((result.intent.details or {}).get("risk_audit_summary") or {}).get("operational_policy", {}).get("entry_eligible") is False


def test_runtime_exits_only_operational_policy_blocks_new_autonomous_entry(session, broker, fixed_now, monkeypatch):
    _enable_live_entry_context(monkeypatch)
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    candidate = _candidate(
        strategy_name="smoke_test_hold",
        instrument=INSTRUMENT,
        direction=OrderDirection.BUY,
        signal_at=fixed_now,
        confidence=0.9,
        broker=broker,
        position_size=0.2,
        risk_per_trade=0.1,
    )
    candidate.engine.runtime_mode = "EXITS_ONLY"

    result = TradeDecisionService(session).decide_signal_candidates([candidate], received_at=fixed_now)[0]

    assert result.admitted is False
    assert result.reason_code == "operational_policy_blocked"
    assert result.intent is not None
    assert result.intent.state == TradeIntentState.REJECTED.value
    assert "runtime_exits_only" in (result.intent.decision_reason or "")
