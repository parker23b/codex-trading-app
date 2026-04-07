from __future__ import annotations

from datetime import timedelta

import pytest
from app.core.broker import BrokerMarketDetails, OrderDirection
from app.core.config import get_settings
from app.core.runtime import runtime_manager
from sqlmodel import select

from app.core.broker import BrokerOrderResult, BrokerOrderStatus
from app.models.runtime import StrategyRuntimeState
from app.models.trade import Execution, ExecutionPhase, ExecutionStatus
from app.services.health_service import get_health_service
from app.services.market_status_service import get_market_status_service
from app.services.strategy_service import StrategyService
from app.services.trade_service import TradeService
from tests.fakes import make_order_result


INSTRUMENT = "CS.D.EURUSD.MINI.IP"
STRATEGY = "smoke_test_hold"


def test_start_and_stop_strategy_persists_runtime_state(session):
    service = StrategyService(session)

    service.start_strategy(STRATEGY, INSTRUMENT)

    runtime = session.exec(
        select(StrategyRuntimeState)
        .where(StrategyRuntimeState.strategy_name == STRATEGY)
        .where(StrategyRuntimeState.instrument == INSTRUMENT)
    ).one()
    assert runtime.status == "RUNNING"
    assert runtime.recovery_state == "RUNNING"

    service.stop_strategy(instrument=INSTRUMENT, strategy_name=STRATEGY)

    stopped_runtime = session.exec(
        select(StrategyRuntimeState).where(StrategyRuntimeState.id == runtime.id)
    ).one()
    assert stopped_runtime.status == "STOPPED"
    assert stopped_runtime.recovery_state == "PAUSED"


def test_prepare_execution_reuses_existing_entry_attempt_for_same_opportunity(session, fixed_now):
    trade_service = TradeService(session)
    initial_execution = trade_service.create_execution(
        Execution(
            strategy_name="mean_reversion",
            instrument=INSTRUMENT,
            phase=ExecutionPhase.ENTRY.value,
            status=ExecutionStatus.ORDER_SUBMITTED.value,
            client_request_id="ent-existing-request",
            signal_time=fixed_now,
            requested_size=1.0,
            requested_price=100.0,
            details={"action_key": f"entry:mean_reversion:{INSTRUMENT}:BUY", "direction": "BUY"},
        )
    )

    execution, should_submit = StrategyService._prepare_execution(
        trade_service=trade_service,
        strategy_name="mean_reversion",
        instrument=INSTRUMENT,
        phase=ExecutionPhase.ENTRY.value,
        signal_time=fixed_now + timedelta(seconds=5),
        requested_size=1.0,
        requested_price=100.2,
        reason="Entry signal generated",
        details={"action_key": f"entry:mean_reversion:{INSTRUMENT}:BUY", "direction": "BUY"},
    )

    executions = trade_service.list_executions(limit=10)
    assert should_submit is True
    assert execution.id == initial_execution.id
    assert execution.client_request_id == "ent-existing-request"
    assert execution.details["duplicate_action_detected"] is True
    assert execution.details["duplicate_attempt_count"] == 1
    assert len(executions) == 1


def test_prepare_execution_blocks_unsafe_duplicate_close_retry(session, fixed_now):
    trade_service = TradeService(session)
    initial_execution = trade_service.create_execution(
        Execution(
            strategy_name="mean_reversion",
            instrument=INSTRUMENT,
            phase=ExecutionPhase.CLOSE.value,
            status=ExecutionStatus.ORDER_SUBMITTED.value,
            client_request_id="cls-existing-request",
            broker_reference="broker-pos-1",
            local_position_id=42,
            signal_time=fixed_now,
            requested_size=1.0,
            requested_price=100.0,
            details={"action_key": f"close:mean_reversion:{INSTRUMENT}:broker-pos-1"},
        )
    )

    execution, should_submit = StrategyService._prepare_execution(
        trade_service=trade_service,
        strategy_name="mean_reversion",
        instrument=INSTRUMENT,
        phase=ExecutionPhase.CLOSE.value,
        signal_time=fixed_now + timedelta(seconds=5),
        requested_size=1.0,
        requested_price=99.8,
        reason="Exit signal generated",
        broker_reference="broker-pos-1",
        local_position_id=42,
        details={"action_key": f"close:mean_reversion:{INSTRUMENT}:broker-pos-1"},
    )

    executions = trade_service.list_executions(limit=10)
    assert should_submit is False
    assert execution.id == initial_execution.id
    assert execution.status == ExecutionStatus.NEEDS_MANUAL_REVIEW.value
    assert execution.requires_manual_review is True
    assert execution.details["duplicate_retry_blocked"] is True
    assert execution.details["duplicate_attempt_count"] == 1
    assert len(executions) == 1


def test_process_price_update_runs_entry_to_close_lifecycle(session, broker, fixed_now):
    service = StrategyService(session)
    trade_service = TradeService(session)
    service.start_strategy(STRATEGY, INSTRUMENT)
    broker.place_order_outcomes.append(
        make_order_result(
            broker_reference="entry-1",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=101.0,
            average_fill_price=101.25,
            executed_at=fixed_now + timedelta(seconds=1),
        )
    )
    broker.close_position_outcomes.append(
        make_order_result(
            broker_reference="close-1",
            instrument=INSTRUMENT,
            direction=OrderDirection.SELL,
            size=0.2,
            price=103.0,
            average_fill_price=102.75,
            executed_at=fixed_now + timedelta(seconds=40),
        )
    )

    service.process_price_update(INSTRUMENT, 100.0, bid=99.99, ask=100.01, market_status="TRADEABLE", tradable=True, received_at=fixed_now)
    service.process_price_update(INSTRUMENT, 101.0, bid=100.99, ask=101.01, market_status="TRADEABLE", tradable=True, received_at=fixed_now + timedelta(seconds=1))

    open_positions = trade_service.list_positions()
    assert len(open_positions) == 1
    assert open_positions[0].broker_reference == "entry-1"
    assert open_positions[0].open_price == 101.25

    service.process_price_update(INSTRUMENT, 103.0, bid=102.8, ask=103.2, market_status="TRADEABLE", tradable=True, received_at=fixed_now + timedelta(seconds=40))

    trades = trade_service.list_trades()
    executions = trade_service.list_executions(limit=10)
    assert len(trade_service.list_positions()) == 0
    assert len(trades) == 1
    assert trades[0].close_broker_reference == "close-1"
    assert trades[0].pnl == pytest.approx(0.3)
    assert trades[0].r_multiple == pytest.approx(3.0)
    assert {execution.status for execution in executions} >= {
        ExecutionStatus.POSITION_OPENED.value,
        ExecutionStatus.CLOSE_CONFIRMED.value,
    }


def test_entry_broker_failure_fails_safely_without_opening_position(session, broker, fixed_now):
    service = StrategyService(session)
    trade_service = TradeService(session)
    service.start_strategy(STRATEGY, INSTRUMENT)
    broker.place_order_outcomes.append(RuntimeError("entry endpoint timeout"))

    service.process_price_update(INSTRUMENT, 100.0, bid=99.99, ask=100.01, market_status="TRADEABLE", tradable=True, received_at=fixed_now)
    service.process_price_update(INSTRUMENT, 100.5, bid=100.49, ask=100.51, market_status="TRADEABLE", tradable=True, received_at=fixed_now + timedelta(seconds=1))

    executions = trade_service.list_executions(limit=10)
    engine = session.exec(
        select(StrategyRuntimeState)
        .where(StrategyRuntimeState.strategy_name == STRATEGY)
        .where(StrategyRuntimeState.instrument == INSTRUMENT)
    ).one()

    assert len(broker.placed_orders) == 1
    assert len(trade_service.list_positions()) == 0
    assert len(trade_service.list_trades()) == 0
    assert executions[0].status == ExecutionStatus.FAILED.value
    assert executions[0].reason == "Entry order submission failed"
    assert executions[0].error_message == "entry endpoint timeout"
    assert engine.current_position_broker_reference is None


def test_entry_below_broker_minimum_is_risk_rejected_before_submission(session, broker, fixed_now):
    service = StrategyService(session)
    trade_service = TradeService(session)
    instrument = "CS.D.EURUSD.CFD.IP"
    strategy = STRATEGY
    broker.market_details_by_instrument[instrument] = BrokerMarketDetails(
        instrument=instrument,
        name=instrument,
        bid=1.1571,
        offer=1.15716,
        high=1.16,
        low=1.15,
        percentage_change=0.0,
        net_change=0.0,
        market_status="TRADEABLE",
        update_time=fixed_now.isoformat(),
        tradable=True,
        min_deal_size=1.0,
    )
    service.start_strategy(strategy, instrument)
    engine = runtime_manager.get_engine(strategy, instrument)
    assert engine is not None
    engine.trade_size = 0.6

    service.process_price_update(
        instrument,
        1.15713,
        bid=1.1571,
        ask=1.15716,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now,
    )
    service.process_price_update(
        instrument,
        1.15713,
        bid=1.1571,
        ask=1.15716,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now + timedelta(seconds=1),
    )

    executions = trade_service.list_executions(limit=10)

    assert broker.placed_orders == []
    assert len(trade_service.list_positions()) == 0
    assert executions[0].status == ExecutionStatus.RISK_REJECTED.value
    assert executions[0].reason == "Requested size 0.6 is below broker minimum deal size 1.0 for CS.D.EURUSD.CFD.IP."
    assert executions[0].details["risk_rejection_layer"] == "broker_constraints"
    assert executions[0].details["risk_audit_summary"]["min_deal_size"] == 1.0


def test_entry_is_blocked_when_market_quote_is_stale(session, broker, fixed_now):
    service = StrategyService(session)
    trade_service = TradeService(session)
    service.start_strategy(STRATEGY, INSTRUMENT)
    market_status_service = get_market_status_service()
    original_get_status = market_status_service.get_status

    def stale_get_status(instrument: str, *, broker=None, now=None):
        status = original_get_status(instrument, broker=broker, now=now)
        return status.model_copy(update={"is_ok": False, "reason": "Latest quote is stale at 2000.0ms old.", "quote_fresh": False})

    market_status_service.get_status = stale_get_status
    try:
        service.process_price_update(
            INSTRUMENT,
            100.0,
            bid=99.99,
            ask=100.01,
            market_status="TRADEABLE",
            tradable=True,
            received_at=fixed_now,
        )
        service.process_price_update(
            INSTRUMENT,
            100.5,
            bid=100.49,
            ask=100.51,
            market_status="TRADEABLE",
            tradable=True,
            received_at=fixed_now + timedelta(seconds=1),
        )
    finally:
        market_status_service.get_status = original_get_status

    executions = trade_service.list_executions(limit=10)
    assert broker.placed_orders == []
    assert len(trade_service.list_positions()) == 0
    assert executions[0].status == ExecutionStatus.RISK_REJECTED.value
    assert executions[0].details["risk_rejection_layer"] == "market_status"
    assert "stale" in executions[0].reason.lower()


def test_entry_is_blocked_when_spread_exceeds_threshold(session, broker, fixed_now):
    service = StrategyService(session)
    trade_service = TradeService(session)
    settings = get_settings()
    settings.max_spread_pips = 0.00005
    broker.market_details_by_instrument[INSTRUMENT] = BrokerMarketDetails(
        instrument=INSTRUMENT,
        name=INSTRUMENT,
        bid=1.10000,
        offer=1.10020,
        high=1.10100,
        low=1.09900,
        percentage_change=0.0,
        net_change=0.0,
        market_status="TRADEABLE",
        update_time=fixed_now.isoformat(),
        tradable=True,
    )
    service.start_strategy(STRATEGY, INSTRUMENT)

    service.process_price_update(INSTRUMENT, 1.10010, bid=1.10000, ask=1.10020, market_status="TRADEABLE", tradable=True, received_at=fixed_now)
    get_market_status_service().reset()
    service.process_price_update(
        INSTRUMENT,
        1.10010,
        bid=1.10000,
        ask=1.10020,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now + timedelta(seconds=1),
    )

    executions = trade_service.list_executions(limit=10)
    assert broker.placed_orders == []
    assert executions[0].status == ExecutionStatus.RISK_REJECTED.value
    assert "spread" in executions[0].reason.lower()


def test_execution_rechecks_market_status_before_order_submission(session, broker, fixed_now):
    service = StrategyService(session)
    trade_service = TradeService(session)
    service.start_strategy(STRATEGY, INSTRUMENT)
    broker.place_order_outcomes.append(
        make_order_result(
            broker_reference="entry-guarded",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=101.0,
            average_fill_price=101.0,
            executed_at=fixed_now + timedelta(seconds=1),
        )
    )

    market_status_service = get_market_status_service()
    original_get_status = market_status_service.get_status
    calls = {"count": 0}

    def guarded_get_status(instrument: str, *, broker=None, now=None):
        calls["count"] += 1
        status = original_get_status(instrument, broker=broker, now=now)
        if calls["count"] >= 2:
            return status.model_copy(update={"is_ok": False, "reason": "Quote turned stale before execution.", "quote_fresh": False})
        return status

    market_status_service.get_status = guarded_get_status
    try:
        service.process_price_update(INSTRUMENT, 100.0, bid=99.99, ask=100.01, market_status="TRADEABLE", tradable=True, received_at=fixed_now)
        service.process_price_update(INSTRUMENT, 100.5, bid=100.49, ask=100.51, market_status="TRADEABLE", tradable=True, received_at=fixed_now + timedelta(seconds=1))
    finally:
        market_status_service.get_status = original_get_status

    executions = trade_service.list_executions(limit=10)
    assert broker.placed_orders == []
    assert executions[0].status == ExecutionStatus.FAILED.value
    assert "execution blocked by market status" in executions[0].reason.lower()
    assert get_health_service().get_health_report()["details"].order_failures_last_5m == 0


def test_close_failure_keeps_position_open_and_flags_manual_review(session, broker, fixed_now):
    service = StrategyService(session)
    trade_service = TradeService(session)
    service.start_strategy(STRATEGY, INSTRUMENT)
    broker.place_order_outcomes.append(
        make_order_result(
            broker_reference="entry-2",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.5,
            executed_at=fixed_now + timedelta(seconds=1),
        )
    )
    broker.close_position_outcomes.append(RuntimeError("close endpoint timeout"))

    service.process_price_update(INSTRUMENT, 100.0, bid=99.99, ask=100.01, market_status="TRADEABLE", tradable=True, received_at=fixed_now)
    service.process_price_update(INSTRUMENT, 100.5, bid=100.49, ask=100.51, market_status="TRADEABLE", tradable=True, received_at=fixed_now + timedelta(seconds=1))
    service.process_price_update(INSTRUMENT, 101.0, bid=100.9, ask=101.1, market_status="TRADEABLE", tradable=True, received_at=fixed_now + timedelta(seconds=40))

    executions = trade_service.list_executions(limit=10)
    assert len(trade_service.list_positions()) == 1
    assert len(trade_service.list_trades()) == 0
    assert executions[0].status == ExecutionStatus.NEEDS_MANUAL_REVIEW.value
    assert executions[0].requires_manual_review is True


def test_partial_close_result_moves_execution_to_manual_review(session, broker, fixed_now):
    service = StrategyService(session)
    trade_service = TradeService(session)
    service.start_strategy(STRATEGY, INSTRUMENT)
    broker.place_order_outcomes.append(
        make_order_result(
            broker_reference="entry-3",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.5,
            executed_at=fixed_now + timedelta(seconds=1),
        )
    )
    broker.close_position_outcomes.append(
        BrokerOrderResult(
            broker_reference="close-partial-1",
            instrument=INSTRUMENT,
            direction=OrderDirection.SELL,
            size=0.2,
            price=101.0,
            executed_at=fixed_now + timedelta(seconds=40),
            status=BrokerOrderStatus.PARTIALLY_FILLED,
            filled_size=0.1,
            average_fill_price=101.0,
            submitted_at=fixed_now + timedelta(seconds=40),
            acknowledged_at=fixed_now + timedelta(seconds=40),
            requires_manual_review=True,
        )
    )

    service.process_price_update(INSTRUMENT, 100.0, bid=99.99, ask=100.01, market_status="TRADEABLE", tradable=True, received_at=fixed_now)
    service.process_price_update(INSTRUMENT, 100.5, bid=100.49, ask=100.51, market_status="TRADEABLE", tradable=True, received_at=fixed_now + timedelta(seconds=1))
    service.process_price_update(INSTRUMENT, 101.0, bid=100.99, ask=101.01, market_status="TRADEABLE", tradable=True, received_at=fixed_now + timedelta(seconds=40))

    executions = trade_service.list_executions(limit=10)
    assert len(trade_service.list_positions()) == 1
    assert len(trade_service.list_trades()) == 0
    assert executions[0].status == ExecutionStatus.NEEDS_MANUAL_REVIEW.value
    assert executions[0].requires_manual_review is True
    assert executions[0].phase == ExecutionPhase.CLOSE.value
    assert executions[0].filled_size == 0.1
    assert executions[0].average_fill_price == 101.0


def test_open_pnl_and_mark_price_helpers_use_directional_pricing():
    assert StrategyService._mark_price(direction="BUY", price=100.0, bid=99.8, ask=100.2) == 99.8
    assert StrategyService._mark_price(direction="SELL", price=100.0, bid=99.8, ask=100.2) == 100.2
    assert StrategyService._calculate_open_pnl(direction="BUY", open_price=100.0, current_price=101.5, size=2.0) == 3.0
    assert StrategyService._calculate_open_pnl(direction="SELL", open_price=100.0, current_price=98.5, size=2.0) == 3.0
