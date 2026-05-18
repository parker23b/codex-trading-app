from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from app.core.broker import (
    AccountType,
    BrokerAccountSummary,
    BrokerMarketDetails,
    BrokerSizingMode,
    BrokerSizingPrecision,
    OrderDirection,
)
from app.core.config import get_settings
from app.core.runtime import runtime_manager
from app.core.signals import EntrySignal, SignalCandidate, SignalKind
from sqlmodel import select

from app.core.broker import (
    BrokerOrderResult,
    BrokerExecutionSource,
    BrokerOrderStatus,
    BrokerRiskSizingQuote,
)
from app.models.runtime import StrategyRuntimeState
from app.models.strategy_deployment import StrategyDeployment
from app.models.trade import (
    Execution,
    ExecutionPhase,
    ExecutionStatus,
    Position,
    TradeIntent,
    TradeIntentState,
)
from app.services.health_service import get_health_service
from app.services.market_status_service import MarketStatus, get_market_status_service
from app.services.strategy_service import StrategyService
from app.services.trade_service import TradeService
from tests.fakes import make_order_result


INSTRUMENT = "CS.D.EURUSD.MINI.IP"
STRATEGY = "smoke_test_hold"


def _enable_live_operational_context(
    monkeypatch: pytest.MonkeyPatch, fixed_now
) -> None:
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
            )(),
            "get_last_tick_at": lambda self, instrument: now,
        },
    )()
    monkeypatch.setattr(
        "app.services.operational_state_service.get_operational_streaming_service",
        lambda: stub,
    )


@pytest.fixture(autouse=True)
def _live_operational_context(monkeypatch: pytest.MonkeyPatch, fixed_now) -> None:
    _enable_live_operational_context(monkeypatch, fixed_now)


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


def test_prepare_execution_reuses_existing_entry_attempt_for_same_opportunity(
    session, fixed_now
):
    trade_service = TradeService(session)
    initial_execution = trade_service.create_execution(
        Execution(
            strategy_name="mean_reversion",
            instrument=INSTRUMENT,
            phase=ExecutionPhase.ENTRY.value,
            status=ExecutionStatus.SUBMISSION_PENDING.value,
            client_request_id="ent-existing-request",
            signal_time=fixed_now,
            requested_size=1.0,
            requested_price=100.0,
            details={
                "action_key": f"entry:mean_reversion:{INSTRUMENT}:BUY",
                "direction": "BUY",
            },
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
        details={
            "action_key": f"entry:mean_reversion:{INSTRUMENT}:BUY",
            "direction": "BUY",
        },
    )

    executions = trade_service.list_executions(limit=10)
    assert should_submit is True
    assert execution.id == initial_execution.id
    assert execution.client_request_id == "ent-existing-request"
    assert execution.details["duplicate_action_detected"] is True
    assert execution.details["duplicate_attempt_count"] == 1
    assert len(executions) == 1


def test_audit_life_001_blocks_submitted_entry_duplicate_retry_until_review(
    session, fixed_now
):
    trade_service = TradeService(session)
    initial_execution = trade_service.create_execution(
        Execution(
            strategy_name="mean_reversion",
            instrument=INSTRUMENT,
            phase=ExecutionPhase.ENTRY.value,
            status=ExecutionStatus.ORDER_SUBMITTED.value,
            client_request_id="ent-submitted-request",
            signal_time=fixed_now,
            requested_size=1.0,
            requested_price=100.0,
            details={
                "action_key": f"entry:mean_reversion:{INSTRUMENT}:BUY",
                "direction": "BUY",
            },
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
        details={
            "action_key": f"entry:mean_reversion:{INSTRUMENT}:BUY",
            "direction": "BUY",
        },
    )

    executions = trade_service.list_executions(limit=10)
    assert should_submit is False
    assert execution.id == initial_execution.id
    assert execution.client_request_id == "ent-submitted-request"
    assert execution.status == ExecutionStatus.NEEDS_MANUAL_REVIEW.value
    assert execution.requires_manual_review is True
    assert execution.details["duplicate_retry_blocked"] is True
    assert execution.details["duplicate_attempt_count"] == 1
    assert execution.details["blocked_duplicate_client_request_id"] == (
        "ent-submitted-request"
    )
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


def test_execute_entry_signal_requires_approved_trade_intent(
    session, broker, fixed_now
):
    trade_service = TradeService(session)
    intent = trade_service.create_trade_intent(
        TradeIntent(
            strategy_name="smoke_test_hold",
            instrument=INSTRUMENT,
            direction="BUY",
            state=TradeIntentState.PROPOSED.value,
            signal_time=fixed_now,
            proposed_size=0.2,
            allocated_size=0.2,
            proposed_risk_percent=0.1,
            allocated_risk_percent=0.1,
        )
    )
    execution = trade_service.create_execution(
        Execution(
            trade_intent_id=intent.id,
            strategy_name="smoke_test_hold",
            instrument=INSTRUMENT,
            phase=ExecutionPhase.ENTRY.value,
            status=ExecutionStatus.SUBMISSION_PENDING.value,
            client_request_id="ent-unapproved",
            signal_time=fixed_now,
            requested_size=0.2,
            requested_price=100.0,
        )
    )
    signal = EntrySignal(
        kind=SignalKind.ENTRY,
        strategy_name="smoke_test_hold",
        instrument=INSTRUMENT,
        observed_price=100.0,
        signal_at=fixed_now,
        direction=OrderDirection.BUY,
        size=0.2,
        risk_percent=0.1,
        bid=99.9,
        ask=100.1,
        market_status="TRADEABLE",
        tradable=True,
    )
    engine = runtime_manager.start(
        strategy_name="smoke_test_hold", instrument=INSTRUMENT
    )

    with pytest.raises(ValueError, match="APPROVED trade intent"):
        StrategyService._execute_entry_signal(
            engine=engine,
            signal=signal,
            intent=intent,
            trade_service=trade_service,
            execution=execution,
        )

    assert broker.placed_orders == []


def test_execute_entry_signal_reuses_broker_normalization_for_revalidation(
    session, broker, fixed_now
):
    trade_service = TradeService(session)
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    broker.market_details_by_instrument[INSTRUMENT] = BrokerMarketDetails(
        instrument=INSTRUMENT,
        name=INSTRUMENT,
        bid=100.0,
        offer=100.1,
        high=101.0,
        low=99.0,
        percentage_change=0.0,
        net_change=0.0,
        market_status="TRADEABLE",
        update_time=fixed_now.isoformat(),
        tradable=True,
        size_step=0.1,
    )
    intent = trade_service.create_trade_intent(
        TradeIntent(
            strategy_name="smoke_test_hold",
            instrument=INSTRUMENT,
            direction="BUY",
            state=TradeIntentState.APPROVED.value,
            signal_time=fixed_now,
            proposed_size=0.23,
            allocated_size=0.23,
            proposed_risk_percent=0.1,
            allocated_risk_percent=0.1,
        )
    )
    execution = trade_service.create_execution(
        Execution(
            trade_intent_id=intent.id,
            strategy_name="smoke_test_hold",
            instrument=INSTRUMENT,
            phase=ExecutionPhase.ENTRY.value,
            status=ExecutionStatus.SUBMISSION_PENDING.value,
            client_request_id="ent-revalidate",
            signal_time=fixed_now,
            requested_size=0.23,
            requested_price=100.0,
        )
    )
    signal = EntrySignal(
        kind=SignalKind.ENTRY,
        strategy_name="smoke_test_hold",
        instrument=INSTRUMENT,
        observed_price=100.0,
        signal_at=fixed_now,
        direction=OrderDirection.BUY,
        size=0.23,
        risk_percent=0.1,
        bid=99.9,
        ask=100.1,
        market_status="TRADEABLE",
        tradable=True,
    )
    engine = runtime_manager.start(
        strategy_name="smoke_test_hold", instrument=INSTRUMENT
    )
    market_status_service = get_market_status_service()
    original_get_status = market_status_service.get_status

    def always_ok_status(instrument, *, broker=None, now=None, force_refresh=False):
        return MarketStatus(
            instrument=instrument,
            is_ok=True,
            market_open=True,
            tradable=True,
            quote_fresh=True,
            spread_ok=True,
            session_valid=True,
            dealing_allowed=True,
            last_price_age_ms=0.0,
            spread=0.1,
            reason=None,
        )

    market_status_service.get_status = always_ok_status

    try:
        with pytest.raises(ValueError, match="reallocation required"):
            StrategyService._execute_entry_signal(
                engine=engine,
                signal=signal,
                intent=intent,
                trade_service=trade_service,
                execution=execution,
            )
    finally:
        market_status_service.get_status = original_get_status

    assert broker.placed_orders == []


def test_audit_risk_002_execution_revalidates_account_before_submission(
    session, broker, fixed_now, monkeypatch
):
    trade_service = TradeService(session)
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    broker.place_order_outcomes.append(
        make_order_result(
            broker_reference="entry-account-drift",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.0,
            executed_at=fixed_now + timedelta(seconds=1),
        )
    )

    def account_unavailable():
        raise RuntimeError("account temporarily unavailable")

    monkeypatch.setattr(broker, "get_account_summary", account_unavailable)
    intent = trade_service.create_trade_intent(
        TradeIntent(
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            direction="BUY",
            state=TradeIntentState.APPROVED.value,
            signal_time=fixed_now,
            proposed_size=0.2,
            allocated_size=0.2,
            proposed_risk_percent=0.1,
            allocated_risk_percent=0.1,
            estimated_risk_amount=100.0,
        )
    )
    execution = trade_service.create_execution(
        Execution(
            trade_intent_id=intent.id,
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            phase=ExecutionPhase.ENTRY.value,
            status=ExecutionStatus.SUBMISSION_PENDING.value,
            client_request_id="ent-account-drift",
            signal_time=fixed_now,
            requested_size=0.2,
            requested_price=100.0,
        )
    )
    engine = runtime_manager.start(strategy_name=STRATEGY, instrument=INSTRUMENT)

    with pytest.raises(ValueError, match="account"):
        StrategyService._execute_entry_signal(
            engine=engine,
            signal=EntrySignal(
                kind=SignalKind.ENTRY,
                strategy_name=STRATEGY,
                instrument=INSTRUMENT,
                observed_price=100.0,
                signal_at=fixed_now,
                direction=OrderDirection.BUY,
                size=0.2,
                risk_percent=0.1,
                bid=99.9,
                ask=100.1,
                market_status="TRADEABLE",
                tradable=True,
            ),
            intent=intent,
            trade_service=trade_service,
            execution=execution,
        )

    assert broker.placed_orders == []
    assert execution.status == ExecutionStatus.FAILED.value
    assert intent.state == TradeIntentState.FAILED.value
    assert execution.details["execution_revalidation"]["layer"] == "account"
    assert (
        intent.details["allocation_outcome"]["stage"] == "execution_revalidation_failed"
    )


def test_audit_life_005_simulated_entry_persists_non_broker_provenance(
    session, broker, fixed_now
):
    trade_service = TradeService(session)
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    broker.place_order_outcomes.append(
        BrokerOrderResult(
            broker_reference="sim-entry-provenance",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.0,
            executed_at=fixed_now + timedelta(seconds=1),
            filled_size=0.2,
            average_fill_price=100.0,
            submitted_at=fixed_now,
            acknowledged_at=fixed_now + timedelta(milliseconds=100),
            execution_source=BrokerExecutionSource.SIMULATED_LOCAL_FILL,
        )
    )
    intent = trade_service.create_trade_intent(
        TradeIntent(
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            direction="BUY",
            state=TradeIntentState.APPROVED.value,
            signal_time=fixed_now,
            proposed_size=0.2,
            allocated_size=0.2,
            proposed_risk_percent=0.1,
            allocated_risk_percent=0.1,
            estimated_risk_amount=100.0,
        )
    )
    execution = trade_service.create_execution(
        Execution(
            trade_intent_id=intent.id,
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            phase=ExecutionPhase.ENTRY.value,
            status=ExecutionStatus.SUBMISSION_PENDING.value,
            client_request_id="ent-simulated-provenance",
            signal_time=fixed_now,
            requested_size=0.2,
            requested_price=100.0,
        )
    )
    engine = runtime_manager.start(strategy_name=STRATEGY, instrument=INSTRUMENT)

    position = StrategyService._execute_entry_signal(
        engine=engine,
        signal=EntrySignal(
            kind=SignalKind.ENTRY,
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            observed_price=100.0,
            signal_at=fixed_now,
            direction=OrderDirection.BUY,
            size=0.2,
            risk_percent=0.1,
            bid=99.9,
            ask=100.1,
            market_status="TRADEABLE",
            tradable=True,
        ),
        intent=intent,
        trade_service=trade_service,
        execution=execution,
    )

    persisted_position = session.exec(select(Position)).one()
    assert position.broker_reference == "sim-entry-provenance"
    assert execution.details["broker_result"]["execution_source"] == (
        BrokerExecutionSource.SIMULATED_LOCAL_FILL.value
    )
    assert intent.details["broker_result"]["execution_source"] == (
        BrokerExecutionSource.SIMULATED_LOCAL_FILL.value
    )
    assert persisted_position.broker_sync_status == (
        BrokerExecutionSource.SIMULATED_LOCAL_FILL.value
    )
    assert persisted_position.broker_open_confirmed_at is None


def test_audit_risk_002_execution_blocks_material_account_equity_drift(
    session, broker, fixed_now
):
    trade_service = TradeService(session)
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    get_settings().allocation_drift_warning_percent = 10.0
    broker.account_summary = BrokerAccountSummary(
        account_id="drifted-account",
        balance=10_000.0,
        available=10_000.0,
        profit_loss=-90_000.0,
        equity=10_000.0,
        account_type=AccountType.DEMO,
    )
    broker.place_order_outcomes.append(
        make_order_result(
            broker_reference="entry-account-equity-drift",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.0,
            executed_at=fixed_now + timedelta(seconds=1),
        )
    )
    intent = trade_service.create_trade_intent(
        TradeIntent(
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            direction="BUY",
            state=TradeIntentState.APPROVED.value,
            signal_time=fixed_now,
            proposed_size=0.2,
            allocated_size=0.2,
            proposed_risk_percent=0.1,
            allocated_risk_percent=0.1,
            estimated_risk_amount=100.0,
            details={
                "allocation": {
                    "account_equity": 100_000.0,
                    "risk_amount": 100.0,
                    "allocated_risk_percent": 0.1,
                    "normalized_size": 0.2,
                    "sizing_details": {
                        "stop_distance_price": 1.0,
                    },
                }
            },
        )
    )
    execution = trade_service.create_execution(
        Execution(
            trade_intent_id=intent.id,
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            phase=ExecutionPhase.ENTRY.value,
            status=ExecutionStatus.SUBMISSION_PENDING.value,
            client_request_id="ent-account-equity-drift",
            signal_time=fixed_now,
            requested_size=0.2,
            requested_price=100.0,
        )
    )
    engine = runtime_manager.start(strategy_name=STRATEGY, instrument=INSTRUMENT)

    with pytest.raises(ValueError, match="account equity drift"):
        StrategyService._execute_entry_signal(
            engine=engine,
            signal=EntrySignal(
                kind=SignalKind.ENTRY,
                strategy_name=STRATEGY,
                instrument=INSTRUMENT,
                observed_price=100.0,
                signal_at=fixed_now,
                direction=OrderDirection.BUY,
                size=0.2,
                risk_percent=0.1,
                bid=99.9,
                ask=100.1,
                market_status="TRADEABLE",
                tradable=True,
            ),
            intent=intent,
            trade_service=trade_service,
            execution=execution,
        )

    assert broker.placed_orders == []
    assert execution.status == ExecutionStatus.FAILED.value
    assert intent.state == TradeIntentState.FAILED.value
    revalidation = execution.details["execution_revalidation"]
    assert revalidation["layer"] == "account"
    assert revalidation["reason_code"] == "account_equity_drift"
    assert revalidation["risk_percent_drift"]["material"] is True
    assert revalidation["risk_percent_drift"]["actual"] == pytest.approx(1.0)
    assert (
        intent.details["allocation_outcome"]["stage"] == "execution_revalidation_failed"
    )


def test_audit_risk_002_execution_blocks_available_funds_below_approved_risk(
    session, broker, fixed_now
):
    trade_service = TradeService(session)
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    broker.account_summary = BrokerAccountSummary(
        account_id="depleted-available",
        balance=100_000.0,
        available=50.0,
        profit_loss=0.0,
        equity=100_000.0,
        account_type=AccountType.DEMO,
    )
    broker.place_order_outcomes.append(
        make_order_result(
            broker_reference="entry-available-drift",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.0,
            executed_at=fixed_now + timedelta(seconds=1),
        )
    )
    intent = trade_service.create_trade_intent(
        TradeIntent(
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            direction="BUY",
            state=TradeIntentState.APPROVED.value,
            signal_time=fixed_now,
            proposed_size=0.2,
            allocated_size=0.2,
            proposed_risk_percent=0.1,
            allocated_risk_percent=0.1,
            estimated_risk_amount=100.0,
            details={
                "allocation": {
                    "account_equity": 100_000.0,
                    "risk_amount": 100.0,
                    "allocated_risk_percent": 0.1,
                    "normalized_size": 0.2,
                    "sizing_details": {
                        "stop_distance_price": 1.0,
                    },
                }
            },
        )
    )
    execution = trade_service.create_execution(
        Execution(
            trade_intent_id=intent.id,
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            phase=ExecutionPhase.ENTRY.value,
            status=ExecutionStatus.SUBMISSION_PENDING.value,
            client_request_id="ent-available-drift",
            signal_time=fixed_now,
            requested_size=0.2,
            requested_price=100.0,
        )
    )
    engine = runtime_manager.start(strategy_name=STRATEGY, instrument=INSTRUMENT)

    with pytest.raises(ValueError, match="available funds"):
        StrategyService._execute_entry_signal(
            engine=engine,
            signal=EntrySignal(
                kind=SignalKind.ENTRY,
                strategy_name=STRATEGY,
                instrument=INSTRUMENT,
                observed_price=100.0,
                signal_at=fixed_now,
                direction=OrderDirection.BUY,
                size=0.2,
                risk_percent=0.1,
                bid=99.9,
                ask=100.1,
                market_status="TRADEABLE",
                tradable=True,
            ),
            intent=intent,
            trade_service=trade_service,
            execution=execution,
        )

    assert broker.placed_orders == []
    assert execution.status == ExecutionStatus.FAILED.value
    assert intent.state == TradeIntentState.FAILED.value
    revalidation = execution.details["execution_revalidation"]
    assert revalidation["layer"] == "account"
    assert revalidation["reason_code"] == "account_available_below_risk"
    assert revalidation["account_available"] == pytest.approx(50.0)
    assert revalidation["risk_amount"] == pytest.approx(100.0)


def test_audit_risk_002_execution_revalidates_sizing_quote_before_submission(
    session, broker, fixed_now
):
    trade_service = TradeService(session)
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    broker.market_details_by_instrument[INSTRUMENT] = BrokerMarketDetails(
        instrument=INSTRUMENT,
        name=INSTRUMENT,
        bid=100.0,
        offer=100.1,
        high=101.0,
        low=99.0,
        percentage_change=0.0,
        net_change=0.0,
        market_status="TRADEABLE",
        update_time=datetime.now(UTC).isoformat(),
        tradable=True,
        metadata={
            "sizing_profile": {
                "mode": BrokerSizingMode.UNSUPPORTED.value,
            }
        },
    )
    broker.place_order_outcomes.append(
        make_order_result(
            broker_reference="entry-sizing-drift",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.0,
            executed_at=fixed_now + timedelta(seconds=1),
        )
    )
    intent = trade_service.create_trade_intent(
        TradeIntent(
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            direction="BUY",
            state=TradeIntentState.APPROVED.value,
            signal_time=fixed_now,
            proposed_size=0.2,
            allocated_size=0.2,
            proposed_risk_percent=0.1,
            allocated_risk_percent=0.1,
            estimated_risk_amount=100.0,
            details={
                "allocation": {
                    "sizing_details": {
                        "stop_distance_price": 1.0,
                    }
                }
            },
        )
    )
    execution = trade_service.create_execution(
        Execution(
            trade_intent_id=intent.id,
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            phase=ExecutionPhase.ENTRY.value,
            status=ExecutionStatus.SUBMISSION_PENDING.value,
            client_request_id="ent-sizing-drift",
            signal_time=fixed_now,
            requested_size=0.2,
            requested_price=100.0,
        )
    )
    engine = runtime_manager.start(strategy_name=STRATEGY, instrument=INSTRUMENT)

    with pytest.raises(ValueError, match="sizing"):
        StrategyService._execute_entry_signal(
            engine=engine,
            signal=EntrySignal(
                kind=SignalKind.ENTRY,
                strategy_name=STRATEGY,
                instrument=INSTRUMENT,
                observed_price=100.0,
                signal_at=fixed_now,
                direction=OrderDirection.BUY,
                size=0.2,
                risk_percent=0.1,
                bid=99.9,
                ask=100.1,
                market_status="TRADEABLE",
                tradable=True,
            ),
            intent=intent,
            trade_service=trade_service,
            execution=execution,
        )

    assert broker.placed_orders == []
    assert execution.status == ExecutionStatus.FAILED.value
    assert intent.state == TradeIntentState.FAILED.value
    assert execution.details["execution_revalidation"]["layer"] == "sizing_quote"
    assert (
        intent.details["execution_revalidation"]["reason_code"] == "unsupported_sizing"
    )


def test_audit_broker_004_execution_risk_snapshot_uses_first_class_sizing_quote_currency(
    broker, fixed_now
):
    broker.market_details_by_instrument[INSTRUMENT] = BrokerMarketDetails(
        instrument=INSTRUMENT,
        name=INSTRUMENT,
        bid=100.0,
        offer=100.1,
        high=101.0,
        low=99.0,
        percentage_change=0.0,
        net_change=0.0,
        market_status="TRADEABLE",
        update_time=fixed_now.isoformat(),
        tradable=True,
        metadata={
            "sizing_profile": {
                "mode": BrokerSizingMode.EXACT_CONTRACT_RISK.value,
                "contract_multiplier": 100.0,
            }
        },
    )
    intent = TradeIntent(
        strategy_name=STRATEGY,
        instrument=INSTRUMENT,
        direction="BUY",
        state=TradeIntentState.APPROVED.value,
        signal_time=fixed_now,
        proposed_size=0.2,
        allocated_size=0.2,
        proposed_risk_percent=0.1,
        allocated_risk_percent=0.1,
        estimated_risk_amount=100.0,
        details={
            "allocation": {
                "account_equity": 100_000.0,
                "risk_amount": 100.0,
                "allocated_risk_percent": 0.1,
                "normalized_size": 0.2,
                "sizing_precision": BrokerSizingPrecision.EXACT.value,
                "sizing_mode": BrokerSizingMode.EXACT_CONTRACT_RISK.value,
                "sizing_details": {
                    "stop_distance_price": 1.0,
                    "sizing_quote": {
                        "account_currency": "USD",
                        "details": {"source": "fake_broker"},
                    },
                },
            }
        },
    )

    snapshot = StrategyService._estimate_execution_risk_snapshot(
        broker=broker,
        intent=intent,
        entry_price=100.0,
        size=0.2,
        risk_state="submitted",
        reservation_owner="EXECUTION",
    )

    assert snapshot["risk_currency"] == "USD"


def test_audit_risk_002_execution_blocks_material_broker_sizing_quote_drift(
    session, broker, fixed_now
):
    trade_service = TradeService(session)
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    get_settings().allocation_drift_warning_percent = 5.0
    broker.market_details_by_instrument[INSTRUMENT] = BrokerMarketDetails(
        instrument=INSTRUMENT,
        name=INSTRUMENT,
        bid=100.0,
        offer=100.1,
        high=101.0,
        low=99.0,
        percentage_change=0.0,
        net_change=0.0,
        market_status="TRADEABLE",
        update_time=datetime.now(UTC).isoformat(),
        tradable=True,
        metadata={
            "sizing_profile": {
                "mode": BrokerSizingMode.EXACT_CONTRACT_RISK.value,
                "contract_multiplier": 200.0,
            }
        },
    )
    broker.place_order_outcomes.append(
        make_order_result(
            broker_reference="entry-sizing-quote-drift",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.0,
            executed_at=fixed_now + timedelta(seconds=1),
        )
    )
    intent = trade_service.create_trade_intent(
        TradeIntent(
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            direction="BUY",
            state=TradeIntentState.APPROVED.value,
            signal_time=fixed_now,
            proposed_size=0.2,
            allocated_size=0.2,
            proposed_risk_percent=0.02,
            allocated_risk_percent=0.02,
            estimated_risk_amount=20.0,
            details={
                "allocation": {
                    "account_equity": 100_000.0,
                    "risk_amount": 20.0,
                    "allocated_risk_percent": 0.02,
                    "normalized_size": 0.2,
                    "sizing_precision": BrokerSizingPrecision.EXACT.value,
                    "sizing_mode": BrokerSizingMode.EXACT_CONTRACT_RISK.value,
                    "sizing_details": {
                        "stop_distance_price": 1.0,
                        "sizing_quote": {
                            "precision": BrokerSizingPrecision.EXACT.value,
                            "mode": BrokerSizingMode.EXACT_CONTRACT_RISK.value,
                            "risk_amount": 20.0,
                            "risk_per_unit": 100.0,
                            "requested_size": 0.2,
                            "normalized_size": 0.2,
                            "stop_distance_price": 1.0,
                            "normalization": {
                                "accepted": True,
                                "reason_code": "normalized",
                                "reason": "Size normalized to broker-valid constraints.",
                                "normalized_size": 0.2,
                                "min_deal_size": None,
                                "size_step": None,
                                "details": {},
                                "notes": [],
                            },
                        },
                    },
                }
            },
        )
    )
    execution = trade_service.create_execution(
        Execution(
            trade_intent_id=intent.id,
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            phase=ExecutionPhase.ENTRY.value,
            status=ExecutionStatus.SUBMISSION_PENDING.value,
            client_request_id="ent-sizing-quote-drift",
            signal_time=fixed_now,
            requested_size=0.2,
            requested_price=100.0,
        )
    )
    engine = runtime_manager.start(strategy_name=STRATEGY, instrument=INSTRUMENT)

    with pytest.raises(ValueError, match="sizing quote drift"):
        StrategyService._execute_entry_signal(
            engine=engine,
            signal=EntrySignal(
                kind=SignalKind.ENTRY,
                strategy_name=STRATEGY,
                instrument=INSTRUMENT,
                observed_price=100.0,
                signal_at=fixed_now,
                direction=OrderDirection.BUY,
                size=0.2,
                risk_percent=0.02,
                bid=99.9,
                ask=100.1,
                market_status="TRADEABLE",
                tradable=True,
            ),
            intent=intent,
            trade_service=trade_service,
            execution=execution,
        )

    assert broker.placed_orders == []
    assert execution.status == ExecutionStatus.FAILED.value
    assert intent.state == TradeIntentState.FAILED.value
    revalidation = execution.details["execution_revalidation"]
    assert revalidation["layer"] == "sizing_quote"
    assert revalidation["reason_code"] == "sizing_quote_drift"
    assert revalidation["approved_sizing_quote_size"] == pytest.approx(0.2)
    assert revalidation["current_sizing_quote_size"] == pytest.approx(0.1)
    assert revalidation["sizing_quote_size_drift"]["material"] is True
    assert (
        intent.details["allocation_outcome"]["stage"] == "execution_revalidation_failed"
    )


def test_audit_risk_002_execution_blocks_material_broker_unit_risk_drift(
    session, broker, fixed_now, monkeypatch
):
    trade_service = TradeService(session)
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    get_settings().allocation_drift_warning_percent = 5.0
    broker.risk_sizing_quote_outcomes[INSTRUMENT] = [
        BrokerRiskSizingQuote(
            instrument=INSTRUMENT,
            precision=BrokerSizingPrecision.EXACT,
            mode=BrokerSizingMode.EXACT_CONTRACT_RISK,
            sizing_available=True,
            reason_code="quoted",
            reason="Broker metadata changed unit risk without changing executable size.",
            entry_price=100.0,
            risk_amount=20.0,
            requested_size=0.16666667,
            normalized_size=0.2,
            risk_per_unit=120.0,
            stop_distance_price=1.0,
        )
    ]
    broker.place_order_outcomes.append(
        make_order_result(
            broker_reference="entry-unit-risk-drift",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.0,
            executed_at=fixed_now + timedelta(seconds=1),
        )
    )
    intent = trade_service.create_trade_intent(
        TradeIntent(
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            direction="BUY",
            state=TradeIntentState.APPROVED.value,
            signal_time=fixed_now,
            proposed_size=0.2,
            allocated_size=0.2,
            proposed_risk_percent=0.02,
            allocated_risk_percent=0.02,
            estimated_risk_amount=20.0,
            details={
                "allocation": {
                    "account_equity": 100_000.0,
                    "risk_amount": 20.0,
                    "allocated_risk_percent": 0.02,
                    "normalized_size": 0.2,
                    "sizing_precision": BrokerSizingPrecision.EXACT.value,
                    "sizing_mode": BrokerSizingMode.EXACT_CONTRACT_RISK.value,
                    "sizing_details": {
                        "stop_distance_price": 1.0,
                        "sizing_quote": {
                            "precision": BrokerSizingPrecision.EXACT.value,
                            "mode": BrokerSizingMode.EXACT_CONTRACT_RISK.value,
                            "risk_amount": 20.0,
                            "risk_per_unit": 100.0,
                            "requested_size": 0.2,
                            "normalized_size": 0.2,
                            "stop_distance_price": 1.0,
                        },
                    },
                }
            },
        )
    )
    execution = trade_service.create_execution(
        Execution(
            trade_intent_id=intent.id,
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            phase=ExecutionPhase.ENTRY.value,
            status=ExecutionStatus.SUBMISSION_PENDING.value,
            client_request_id="ent-unit-risk-drift",
            signal_time=fixed_now,
            requested_size=0.2,
            requested_price=100.0,
        )
    )
    engine = runtime_manager.start(strategy_name=STRATEGY, instrument=INSTRUMENT)
    monkeypatch.setattr(
        get_market_status_service(),
        "get_status",
        lambda instrument, *, broker=None, now=None, force_refresh=False: MarketStatus(
            instrument=instrument,
            is_ok=True,
            market_open=True,
            tradable=True,
            quote_fresh=True,
            spread_ok=True,
            session_valid=True,
            dealing_allowed=True,
            last_price_age_ms=0.0,
            spread=0.1,
            reason=None,
        ),
    )

    with pytest.raises(ValueError, match="sizing quote risk drift"):
        StrategyService._execute_entry_signal(
            engine=engine,
            signal=EntrySignal(
                kind=SignalKind.ENTRY,
                strategy_name=STRATEGY,
                instrument=INSTRUMENT,
                observed_price=100.0,
                signal_at=fixed_now,
                direction=OrderDirection.BUY,
                size=0.2,
                risk_percent=0.02,
                bid=99.9,
                ask=100.1,
                market_status="TRADEABLE",
                tradable=True,
            ),
            intent=intent,
            trade_service=trade_service,
            execution=execution,
        )

    assert broker.placed_orders == []
    assert execution.status == ExecutionStatus.FAILED.value
    assert intent.state == TradeIntentState.FAILED.value
    revalidation = execution.details["execution_revalidation"]
    assert revalidation["layer"] == "sizing_quote"
    assert revalidation["reason_code"] == "sizing_quote_risk_drift"
    assert revalidation["approved_risk_amount"] == pytest.approx(20.0)
    assert revalidation["current_executable_risk_amount"] == pytest.approx(24.0)
    assert revalidation["sizing_quote_risk_drift"]["material"] is True


def test_audit_risk_002_execution_blocks_material_approximate_unit_risk_drift(
    session, broker, fixed_now, monkeypatch
):
    trade_service = TradeService(session)
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    get_settings().allocation_drift_warning_percent = 5.0
    broker.risk_sizing_quote_outcomes[INSTRUMENT] = [
        BrokerRiskSizingQuote(
            instrument=INSTRUMENT,
            precision=BrokerSizingPrecision.APPROXIMATE,
            mode=BrokerSizingMode.APPROXIMATE_PRICE_DELTA,
            sizing_available=True,
            reason_code="quoted",
            reason="Approximate broker metadata changed unit risk.",
            entry_price=100.0,
            risk_amount=20.0,
            requested_size=0.16666667,
            normalized_size=0.2,
            risk_per_unit=120.0,
            stop_distance_price=1.0,
        )
    ]
    broker.place_order_outcomes.append(
        make_order_result(
            broker_reference="entry-approx-risk-drift",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.0,
            executed_at=fixed_now + timedelta(seconds=1),
        )
    )
    intent = trade_service.create_trade_intent(
        TradeIntent(
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            direction="BUY",
            state=TradeIntentState.APPROVED.value,
            signal_time=fixed_now,
            proposed_size=0.2,
            allocated_size=0.2,
            proposed_risk_percent=0.02,
            allocated_risk_percent=0.02,
            estimated_risk_amount=20.0,
            details={
                "allocation": {
                    "account_equity": 100_000.0,
                    "risk_amount": 20.0,
                    "allocated_risk_percent": 0.02,
                    "normalized_size": 0.2,
                    "sizing_precision": BrokerSizingPrecision.APPROXIMATE.value,
                    "sizing_mode": BrokerSizingMode.APPROXIMATE_PRICE_DELTA.value,
                    "sizing_details": {
                        "stop_distance_price": 1.0,
                        "sizing_quote": {
                            "precision": BrokerSizingPrecision.APPROXIMATE.value,
                            "mode": BrokerSizingMode.APPROXIMATE_PRICE_DELTA.value,
                            "risk_amount": 20.0,
                            "risk_per_unit": 100.0,
                            "requested_size": 0.2,
                            "normalized_size": 0.2,
                            "stop_distance_price": 1.0,
                        },
                    },
                }
            },
        )
    )
    execution = trade_service.create_execution(
        Execution(
            trade_intent_id=intent.id,
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            phase=ExecutionPhase.ENTRY.value,
            status=ExecutionStatus.SUBMISSION_PENDING.value,
            client_request_id="ent-approx-risk-drift",
            signal_time=fixed_now,
            requested_size=0.2,
            requested_price=100.0,
        )
    )
    engine = runtime_manager.start(strategy_name=STRATEGY, instrument=INSTRUMENT)
    monkeypatch.setattr(
        get_market_status_service(),
        "get_status",
        lambda instrument, *, broker=None, now=None, force_refresh=False: MarketStatus(
            instrument=instrument,
            is_ok=True,
            market_open=True,
            tradable=True,
            quote_fresh=True,
            spread_ok=True,
            session_valid=True,
            dealing_allowed=True,
            last_price_age_ms=0.0,
            spread=0.1,
            reason=None,
        ),
    )

    with pytest.raises(ValueError, match="sizing quote risk drift"):
        StrategyService._execute_entry_signal(
            engine=engine,
            signal=EntrySignal(
                kind=SignalKind.ENTRY,
                strategy_name=STRATEGY,
                instrument=INSTRUMENT,
                observed_price=100.0,
                signal_at=fixed_now,
                direction=OrderDirection.BUY,
                size=0.2,
                risk_percent=0.02,
                bid=99.9,
                ask=100.1,
                market_status="TRADEABLE",
                tradable=True,
            ),
            intent=intent,
            trade_service=trade_service,
            execution=execution,
        )

    assert broker.placed_orders == []
    assert execution.status == ExecutionStatus.FAILED.value
    assert intent.state == TradeIntentState.FAILED.value
    revalidation = execution.details["execution_revalidation"]
    assert revalidation["layer"] == "sizing_quote"
    assert revalidation["reason_code"] == "sizing_quote_risk_drift"
    assert revalidation["precision"] == BrokerSizingPrecision.APPROXIMATE.value
    assert revalidation["approved_risk_amount"] == pytest.approx(20.0)
    assert revalidation["current_executable_risk_amount"] == pytest.approx(24.0)
    assert revalidation["sizing_quote_risk_drift"]["material"] is True


def test_audit_risk_002_execution_blocks_material_approximate_size_drift(
    session, broker, fixed_now, monkeypatch
):
    trade_service = TradeService(session)
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    get_settings().allocation_drift_warning_percent = 5.0
    broker.risk_sizing_quote_outcomes[INSTRUMENT] = [
        BrokerRiskSizingQuote(
            instrument=INSTRUMENT,
            precision=BrokerSizingPrecision.APPROXIMATE,
            mode=BrokerSizingMode.APPROXIMATE_PRICE_DELTA,
            sizing_available=True,
            reason_code="quoted",
            reason="Approximate broker metadata changed executable size.",
            entry_price=100.0,
            risk_amount=20.0,
            requested_size=0.3,
            normalized_size=0.3,
            risk_per_unit=66.66666667,
            stop_distance_price=1.0,
        )
    ]
    broker.place_order_outcomes.append(
        make_order_result(
            broker_reference="entry-approx-size-drift",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.0,
            executed_at=fixed_now + timedelta(seconds=1),
        )
    )
    intent = trade_service.create_trade_intent(
        TradeIntent(
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            direction="BUY",
            state=TradeIntentState.APPROVED.value,
            signal_time=fixed_now,
            proposed_size=0.2,
            allocated_size=0.2,
            proposed_risk_percent=0.02,
            allocated_risk_percent=0.02,
            estimated_risk_amount=20.0,
            details={
                "allocation": {
                    "account_equity": 100_000.0,
                    "risk_amount": 20.0,
                    "allocated_risk_percent": 0.02,
                    "normalized_size": 0.2,
                    "sizing_precision": BrokerSizingPrecision.APPROXIMATE.value,
                    "sizing_mode": BrokerSizingMode.APPROXIMATE_PRICE_DELTA.value,
                    "sizing_details": {
                        "stop_distance_price": 1.0,
                        "sizing_quote": {
                            "precision": BrokerSizingPrecision.APPROXIMATE.value,
                            "mode": BrokerSizingMode.APPROXIMATE_PRICE_DELTA.value,
                            "risk_amount": 20.0,
                            "risk_per_unit": 100.0,
                            "requested_size": 0.2,
                            "normalized_size": 0.2,
                            "stop_distance_price": 1.0,
                        },
                    },
                }
            },
        )
    )
    execution = trade_service.create_execution(
        Execution(
            trade_intent_id=intent.id,
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            phase=ExecutionPhase.ENTRY.value,
            status=ExecutionStatus.SUBMISSION_PENDING.value,
            client_request_id="ent-approx-size-drift",
            signal_time=fixed_now,
            requested_size=0.2,
            requested_price=100.0,
        )
    )
    engine = runtime_manager.start(strategy_name=STRATEGY, instrument=INSTRUMENT)
    monkeypatch.setattr(
        get_market_status_service(),
        "get_status",
        lambda instrument, *, broker=None, now=None, force_refresh=False: MarketStatus(
            instrument=instrument,
            is_ok=True,
            market_open=True,
            tradable=True,
            quote_fresh=True,
            spread_ok=True,
            session_valid=True,
            dealing_allowed=True,
            last_price_age_ms=0.0,
            spread=0.1,
            reason=None,
        ),
    )

    with pytest.raises(ValueError, match="sizing quote drift"):
        StrategyService._execute_entry_signal(
            engine=engine,
            signal=EntrySignal(
                kind=SignalKind.ENTRY,
                strategy_name=STRATEGY,
                instrument=INSTRUMENT,
                observed_price=100.0,
                signal_at=fixed_now,
                direction=OrderDirection.BUY,
                size=0.2,
                risk_percent=0.02,
                bid=99.9,
                ask=100.1,
                market_status="TRADEABLE",
                tradable=True,
            ),
            intent=intent,
            trade_service=trade_service,
            execution=execution,
        )

    assert broker.placed_orders == []
    assert execution.status == ExecutionStatus.FAILED.value
    assert intent.state == TradeIntentState.FAILED.value
    revalidation = execution.details["execution_revalidation"]
    assert revalidation["layer"] == "sizing_quote"
    assert revalidation["reason_code"] == "sizing_quote_drift"
    assert revalidation["precision"] == BrokerSizingPrecision.APPROXIMATE.value
    assert revalidation["approved_sizing_quote_size"] == pytest.approx(0.2)
    assert revalidation["current_sizing_quote_size"] == pytest.approx(0.3)
    assert revalidation["sizing_quote_size_drift"]["material"] is True


def test_audit_risk_002_execution_revalidates_market_status_without_cache(
    session, broker, fixed_now
):
    trade_service = TradeService(session)
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    broker.market_details_by_instrument[INSTRUMENT] = BrokerMarketDetails(
        instrument=INSTRUMENT,
        name=INSTRUMENT,
        bid=100.0,
        offer=100.1,
        high=101.0,
        low=99.0,
        percentage_change=0.0,
        net_change=0.0,
        market_status="TRADEABLE",
        update_time=fixed_now.isoformat(),
        tradable=True,
    )
    cached_status = get_market_status_service().get_status(
        INSTRUMENT, broker=broker, now=fixed_now
    )
    assert cached_status.is_ok is True

    broker.market_details_by_instrument[INSTRUMENT] = BrokerMarketDetails(
        instrument=INSTRUMENT,
        name=INSTRUMENT,
        bid=100.0,
        offer=100.1,
        high=101.0,
        low=99.0,
        percentage_change=0.0,
        net_change=0.0,
        market_status="CLOSED",
        update_time=fixed_now.isoformat(),
        tradable=True,
    )
    broker.place_order_outcomes.append(
        make_order_result(
            broker_reference="entry-stale-market-cache",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.0,
            executed_at=fixed_now + timedelta(seconds=1),
        )
    )
    intent = trade_service.create_trade_intent(
        TradeIntent(
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            direction="BUY",
            state=TradeIntentState.APPROVED.value,
            signal_time=fixed_now,
            proposed_size=0.2,
            allocated_size=0.2,
            proposed_risk_percent=0.1,
            allocated_risk_percent=0.1,
            estimated_risk_amount=100.0,
        )
    )
    execution = trade_service.create_execution(
        Execution(
            trade_intent_id=intent.id,
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            phase=ExecutionPhase.ENTRY.value,
            status=ExecutionStatus.SUBMISSION_PENDING.value,
            client_request_id="ent-market-cache-drift",
            signal_time=fixed_now,
            requested_size=0.2,
            requested_price=100.0,
        )
    )
    engine = runtime_manager.start(strategy_name=STRATEGY, instrument=INSTRUMENT)

    with pytest.raises(RuntimeError, match="closed"):
        StrategyService._execute_entry_signal(
            engine=engine,
            signal=EntrySignal(
                kind=SignalKind.ENTRY,
                strategy_name=STRATEGY,
                instrument=INSTRUMENT,
                observed_price=100.0,
                signal_at=fixed_now,
                direction=OrderDirection.BUY,
                size=0.2,
                risk_percent=0.1,
                bid=99.9,
                ask=100.1,
                market_status="TRADEABLE",
                tradable=True,
            ),
            intent=intent,
            trade_service=trade_service,
            execution=execution,
        )

    assert broker.placed_orders == []
    assert execution.status == ExecutionStatus.FAILED.value
    assert intent.state == TradeIntentState.FAILED.value
    assert execution.details["execution_revalidation"]["layer"] == "market_status"
    assert (
        execution.details["execution_revalidation"]["market_status"]["market_open"]
        is False
    )
    assert (
        intent.details["allocation_outcome"]["stage"] == "execution_revalidation_failed"
    )


def test_audit_risk_002_execution_metadata_failure_before_submission_is_audited(
    session, broker, fixed_now, monkeypatch
):
    trade_service = TradeService(session)
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    market_details = BrokerMarketDetails(
        instrument=INSTRUMENT,
        name=INSTRUMENT,
        bid=100.0,
        offer=100.1,
        high=101.0,
        low=99.0,
        percentage_change=0.0,
        net_change=0.0,
        market_status="TRADEABLE",
        update_time=datetime.now(UTC).isoformat(),
        tradable=True,
    )
    broker.place_order_outcomes.append(
        make_order_result(
            broker_reference="entry-metadata-drift",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.0,
            executed_at=fixed_now + timedelta(seconds=1),
        )
    )
    calls = 0

    def metadata_then_failure(instrument):
        nonlocal calls
        calls += 1
        if calls == 1:
            return market_details
        raise RuntimeError("market metadata unavailable during normalization")

    monkeypatch.setattr(broker, "get_market_details", metadata_then_failure)
    intent = trade_service.create_trade_intent(
        TradeIntent(
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            direction="BUY",
            state=TradeIntentState.APPROVED.value,
            signal_time=fixed_now,
            proposed_size=0.2,
            allocated_size=0.2,
            proposed_risk_percent=0.1,
            allocated_risk_percent=0.1,
            estimated_risk_amount=100.0,
        )
    )
    execution = trade_service.create_execution(
        Execution(
            trade_intent_id=intent.id,
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            phase=ExecutionPhase.ENTRY.value,
            status=ExecutionStatus.SUBMISSION_PENDING.value,
            client_request_id="ent-metadata-drift",
            signal_time=fixed_now,
            requested_size=0.2,
            requested_price=100.0,
        )
    )
    engine = runtime_manager.start(strategy_name=STRATEGY, instrument=INSTRUMENT)

    with pytest.raises(ValueError, match="broker metadata"):
        StrategyService._execute_entry_signal(
            engine=engine,
            signal=EntrySignal(
                kind=SignalKind.ENTRY,
                strategy_name=STRATEGY,
                instrument=INSTRUMENT,
                observed_price=100.0,
                signal_at=fixed_now,
                direction=OrderDirection.BUY,
                size=0.2,
                risk_percent=0.1,
                bid=99.9,
                ask=100.1,
                market_status="TRADEABLE",
                tradable=True,
            ),
            intent=intent,
            trade_service=trade_service,
            execution=execution,
        )

    assert broker.placed_orders == []
    assert execution.status == ExecutionStatus.FAILED.value
    assert intent.state == TradeIntentState.FAILED.value
    assert execution.details["execution_revalidation"]["layer"] == "broker_metadata"
    assert (
        execution.details["execution_revalidation"]["reason_code"]
        == "broker_metadata_unavailable"
    )
    assert (
        intent.details["allocation_outcome"]["stage"] == "execution_revalidation_failed"
    )


def test_process_price_update_runs_entry_to_close_lifecycle(session, broker, fixed_now):
    service = StrategyService(session)
    trade_service = TradeService(session)
    broker.account_summary = BrokerAccountSummary(
        account_id="smoke-lifecycle",
        balance=101.0,
        available=101.0,
        profit_loss=0.0,
        equity=101.0,
        account_type=AccountType.DEMO,
    )
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
        101.0,
        bid=100.99,
        ask=101.01,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now + timedelta(seconds=1),
    )

    open_positions = trade_service.list_positions()
    assert len(open_positions) == 1
    assert open_positions[0].broker_reference == "entry-1"
    assert open_positions[0].open_price == 101.25

    service.process_price_update(
        INSTRUMENT,
        103.0,
        bid=102.8,
        ask=103.2,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now + timedelta(seconds=40),
    )

    trades = trade_service.list_trades()
    executions = trade_service.list_executions(limit=10)
    assert len(trade_service.list_positions()) == 0
    assert len(trades) == 1
    assert trades[0].close_broker_reference == "close-1"
    assert trades[0].pnl == pytest.approx(0.3)
    assert trades[0].r_multiple == pytest.approx(2.97, rel=1e-2)
    assert {execution.status for execution in executions} >= {
        ExecutionStatus.POSITION_OPENED.value,
        ExecutionStatus.CLOSE_CONFIRMED.value,
    }
    assert {execution.status for execution in executions}.isdisjoint(
        {
            ExecutionStatus.SIGNAL_GENERATED.value,
            ExecutionStatus.RISK_APPROVED.value,
            ExecutionStatus.RISK_REJECTED.value,
            ExecutionStatus.CLOSE_REQUESTED.value,
        }
    )


def test_evaluate_price_update_is_decoupled_from_execution_orchestration(
    session, broker, fixed_now
):
    service = StrategyService(session)
    trade_service = TradeService(session)
    broker.account_summary = BrokerAccountSummary(
        account_id="smoke-split",
        balance=101.0,
        available=101.0,
        profit_loss=0.0,
        equity=101.0,
        account_type=AccountType.DEMO,
    )
    service.start_strategy(STRATEGY, INSTRUMENT)
    broker.place_order_outcomes.append(
        make_order_result(
            broker_reference="entry-split-1",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=101.0,
            average_fill_price=101.0,
            executed_at=fixed_now + timedelta(seconds=1),
        )
    )

    service.evaluate_price_update(
        INSTRUMENT,
        100.0,
        bid=99.99,
        ask=100.01,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now,
        source_tier="TIER2",
    )
    candidates = service.evaluate_price_update(
        INSTRUMENT,
        101.0,
        bid=100.99,
        ask=101.01,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now + timedelta(seconds=1),
        source_tier="TIER2",
    )

    assert len(candidates) == 1
    assert candidates[0].source_tier == "TIER2"
    assert candidates[0].signal is not None
    assert broker.placed_orders == []
    assert trade_service.list_executions(limit=10) == []

    service.orchestrate_signal_candidates(
        candidates,
        price=101.0,
        bid=100.99,
        ask=101.01,
        received_at=fixed_now + timedelta(seconds=1),
    )

    executions = trade_service.list_executions(limit=10)
    assert len(broker.placed_orders) == 1
    assert len(executions) == 1
    assert executions[0].status == ExecutionStatus.POSITION_OPENED.value


def test_new_execution_rows_start_at_submission_pending(session, fixed_now):
    trade_service = TradeService(session)

    execution, should_submit = StrategyService._prepare_execution(
        trade_service=trade_service,
        strategy_name="mean_reversion",
        instrument=INSTRUMENT,
        phase=ExecutionPhase.ENTRY.value,
        signal_time=fixed_now,
        requested_size=1.0,
        requested_price=100.0,
        reason="Execution attempt created for approved entry intent",
        details={
            "action_key": f"entry:mean_reversion:{INSTRUMENT}:BUY",
            "direction": "BUY",
        },
    )

    assert should_submit is True
    assert execution.status == ExecutionStatus.SUBMISSION_PENDING.value


def test_allocate_signal_candidates_filters_weaker_conflicting_entries(
    session, broker, fixed_now
):
    service = StrategyService(session)
    instrument = INSTRUMENT
    runtime_manager.last_price_updated_at[instrument] = fixed_now
    broker.market_details_by_instrument[instrument] = BrokerMarketDetails(
        instrument=instrument,
        name=instrument,
        bid=1.1000,
        offer=1.1001,
        high=1.1010,
        low=1.0990,
        percentage_change=0.0,
        net_change=0.0,
        market_status="TRADEABLE",
        update_time=fixed_now.isoformat(),
        tradable=True,
    )
    buy_engine = SimpleNamespace(
        strategy=SimpleNamespace(name="breakout_guard"),
        broker=broker,
        instrument=instrument,
    )
    sell_engine = SimpleNamespace(
        strategy=SimpleNamespace(name="mean_reversion"),
        broker=broker,
        instrument=instrument,
    )
    strong_buy = SignalCandidate(
        strategy_name="breakout_guard",
        instrument=instrument,
        signal=EntrySignal(
            kind=SignalKind.ENTRY,
            strategy_name="breakout_guard",
            instrument=instrument,
            observed_price=1.1001,
            signal_at=fixed_now,
            direction=OrderDirection.BUY,
            size=1.0,
            risk_percent=0.7,
            bid=1.1000,
            ask=1.1001,
            market_status="TRADEABLE",
            tradable=True,
        ),
        engine=buy_engine,
        confidence=0.95,
        metadata=SimpleNamespace(risk_per_trade=0.7),
    )
    sell_conflict = SignalCandidate(
        strategy_name="mean_reversion",
        instrument=instrument,
        signal=EntrySignal(
            kind=SignalKind.ENTRY,
            strategy_name="mean_reversion",
            instrument=instrument,
            observed_price=1.1001,
            signal_at=fixed_now,
            direction=OrderDirection.SELL,
            size=1.0,
            risk_percent=0.7,
            bid=1.1000,
            ask=1.1001,
            market_status="TRADEABLE",
            tradable=True,
        ),
        engine=sell_engine,
        confidence=0.5,
        metadata=SimpleNamespace(risk_per_trade=0.7),
    )

    selected = service.allocate_signal_candidates(
        [sell_conflict, strong_buy], received_at=fixed_now
    )

    assert len(selected) == 1
    assert selected[0].strategy_name == "breakout_guard"


def test_entry_broker_failure_fails_safely_without_opening_position(
    session, broker, fixed_now
):
    service = StrategyService(session)
    trade_service = TradeService(session)
    service.start_strategy(STRATEGY, INSTRUMENT)
    broker.place_order_outcomes.append(RuntimeError("entry endpoint timeout"))

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


def test_entry_below_broker_minimum_is_risk_rejected_before_submission(
    session, broker, fixed_now
):
    service = StrategyService(session)
    trade_service = TradeService(session)
    broker.account_summary = BrokerAccountSummary(
        account_id="min-size-reject",
        balance=1.15713,
        available=1.15713,
        profit_loss=0.0,
        equity=1.15713,
        account_type=AccountType.DEMO,
    )
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

    assert broker.placed_orders == []
    assert len(trade_service.list_positions()) == 0
    assert trade_service.list_executions(limit=10) == []
    intents = trade_service.list_trade_intents(limit=10)
    assert intents[0].state == TradeIntentState.REJECTED.value
    assert "minimum deal size" in (intents[0].decision_reason or "").lower()
    assert intents[0].decision_reason_code == "below_min_size"
    assert intents[0].details["allocation"]["broker_details"]["min_deal_size"] == 1.0


def test_entry_is_blocked_when_market_quote_is_stale(session, broker, fixed_now):
    service = StrategyService(session)
    trade_service = TradeService(session)
    service.start_strategy(STRATEGY, INSTRUMENT)
    market_status_service = get_market_status_service()
    original_get_status = market_status_service.get_status

    def stale_get_status(
        instrument: str, *, broker=None, now=None, force_refresh=False
    ):
        status = original_get_status(
            instrument, broker=broker, now=now, force_refresh=force_refresh
        )
        return status.model_copy(
            update={
                "is_ok": False,
                "reason": "Latest quote is stale at 2000.0ms old.",
                "quote_fresh": False,
            }
        )

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

    assert broker.placed_orders == []
    assert len(trade_service.list_positions()) == 0
    assert trade_service.list_executions(limit=10) == []
    intents = trade_service.list_trade_intents(limit=10)
    assert intents[0].state == TradeIntentState.REJECTED.value
    assert intents[0].details["risk_rejection_layer"] == "market_status"
    assert "stale" in (intents[0].decision_reason or "").lower()


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

    service.process_price_update(
        INSTRUMENT,
        1.10010,
        bid=1.10000,
        ask=1.10020,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now,
    )
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

    assert broker.placed_orders == []
    assert trade_service.list_executions(limit=10) == []
    intents = trade_service.list_trade_intents(limit=10)
    assert intents[0].state == TradeIntentState.REJECTED.value
    assert "spread" in (intents[0].decision_reason or "").lower()


def test_audit_broker_003_unknown_market_status_blocks_entry_even_when_tradable(
    session, broker, fixed_now
):
    service = StrategyService(session)
    trade_service = TradeService(session)
    broker.market_details_by_instrument[INSTRUMENT] = BrokerMarketDetails(
        instrument=INSTRUMENT,
        name=INSTRUMENT,
        bid=100.49,
        offer=100.51,
        high=101.0,
        low=99.0,
        percentage_change=0.0,
        net_change=0.0,
        market_status=None,
        update_time=fixed_now.isoformat(),
        tradable=True,
    )
    broker.place_order_outcomes.append(
        make_order_result(
            broker_reference="entry-should-not-submit",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.5,
            executed_at=fixed_now + timedelta(seconds=1),
        )
    )
    service.start_strategy(STRATEGY, INSTRUMENT)

    service.process_price_update(
        INSTRUMENT,
        100.0,
        bid=99.99,
        ask=100.01,
        market_status=None,
        tradable=True,
        received_at=fixed_now,
    )
    service.process_price_update(
        INSTRUMENT,
        100.5,
        bid=100.49,
        ask=100.51,
        market_status=None,
        tradable=True,
        received_at=fixed_now + timedelta(seconds=1),
    )

    assert broker.placed_orders == []
    assert trade_service.list_executions(limit=10) == []
    intents = trade_service.list_trade_intents(limit=10)
    assert intents[0].state == TradeIntentState.REJECTED.value
    assert intents[0].details["risk_rejection_layer"] == "market_status"
    assert "unknown" in (intents[0].decision_reason or "").lower()


def test_execution_rechecks_market_status_before_order_submission(
    session, broker, fixed_now
):
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

    def guarded_get_status(
        instrument: str, *, broker=None, now=None, force_refresh=False
    ):
        calls["count"] += 1
        status = original_get_status(
            instrument, broker=broker, now=now, force_refresh=force_refresh
        )
        if calls["count"] >= 2:
            return status.model_copy(
                update={
                    "is_ok": False,
                    "reason": "Quote turned stale before execution.",
                    "quote_fresh": False,
                }
            )
        return status

    market_status_service.get_status = guarded_get_status
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
    assert executions[0].status == ExecutionStatus.FAILED.value
    assert "execution blocked by market status" in executions[0].reason.lower()
    assert (
        get_health_service().get_health_report()["details"].order_failures_last_5m == 0
    )


def test_audit_life_001_acknowledged_only_entry_does_not_create_fill_truth(
    session, broker, fixed_now
):
    service = StrategyService(session)
    trade_service = TradeService(session)
    service.start_strategy(STRATEGY, INSTRUMENT)
    broker.place_order_outcomes.append(
        BrokerOrderResult(
            broker_reference="entry-ack-only",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.5,
            executed_at=fixed_now + timedelta(seconds=1),
            status=BrokerOrderStatus.ACKNOWLEDGED,
            requested_size=0.2,
            filled_size=None,
            average_fill_price=None,
            submitted_at=fixed_now + timedelta(seconds=1),
            acknowledged_at=fixed_now + timedelta(seconds=1),
            reason="Broker acknowledged submission but no fill confirmation exists.",
        )
    )

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

    intent = trade_service.list_trade_intents(limit=1)[0]
    execution = trade_service.list_executions(limit=1)[0]

    assert len(trade_service.list_positions()) == 0
    assert intent.state == TradeIntentState.ACKNOWLEDGED.value
    assert intent.filled_size is None
    assert intent.position_id is None
    assert execution.status == ExecutionStatus.NEEDS_MANUAL_REVIEW.value
    assert execution.requires_manual_review is True
    assert execution.filled_size is None
    assert execution.details["broker_result"]["status"] == "ACKNOWLEDGED"


def test_audit_life_001_entry_timeout_preserves_ambiguous_manual_review_state(
    session, broker, fixed_now
):
    service = StrategyService(session)
    trade_service = TradeService(session)
    service.start_strategy(STRATEGY, INSTRUMENT)
    broker.place_order_outcomes.append(TimeoutError("confirmation lookup timed out"))

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

    intent = trade_service.list_trade_intents(limit=1)[0]
    execution = trade_service.list_executions(limit=1)[0]

    assert len(trade_service.list_positions()) == 0
    assert intent.state == TradeIntentState.ACKNOWLEDGED.value
    assert intent.decision_reason_code == "broker_confirmation_ambiguous"
    assert execution.status == ExecutionStatus.NEEDS_MANUAL_REVIEW.value
    assert execution.requires_manual_review is True
    assert execution.error_code == "BROKER_CONFIRMATION_TIMEOUT"
    assert execution.details["broker_result"]["status"] == "TIMED_OUT"


@pytest.mark.parametrize(
    ("broker_status", "error_code"),
    [
        (BrokerOrderStatus.RATE_LIMITED, "BROKER_CONFIRMATION_RATE_LIMITED"),
        (BrokerOrderStatus.UNKNOWN, "BROKER_CONFIRMATION_UNKNOWN"),
    ],
)
def test_audit_life_001_non_final_entry_results_preserve_manual_review_state(
    session, broker, fixed_now, broker_status, error_code
):
    service = StrategyService(session)
    trade_service = TradeService(session)
    service.start_strategy(STRATEGY, INSTRUMENT)
    broker.place_order_outcomes.append(
        BrokerOrderResult(
            broker_reference=f"entry-{broker_status.value.lower()}",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.5,
            executed_at=fixed_now + timedelta(seconds=1),
            status=broker_status,
            requested_size=0.2,
            filled_size=None,
            average_fill_price=None,
            submitted_at=fixed_now + timedelta(seconds=1),
            acknowledged_at=fixed_now + timedelta(seconds=1),
            reason=f"Broker confirmation ended in {broker_status.value}.",
            error_code=error_code,
            requires_manual_review=True,
        )
    )

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

    intent = trade_service.list_trade_intents(limit=1)[0]
    execution = trade_service.list_executions(limit=1)[0]

    assert len(trade_service.list_positions()) == 0
    assert intent.state == TradeIntentState.ACKNOWLEDGED.value
    assert intent.decision_reason_code == "broker_confirmation_ambiguous"
    assert execution.status == ExecutionStatus.NEEDS_MANUAL_REVIEW.value
    assert execution.requires_manual_review is True
    assert execution.error_code == error_code
    assert execution.broker_reference == f"entry-{broker_status.value.lower()}"
    assert execution.client_request_id == broker.placed_orders[0].client_request_id
    assert execution.details["broker_result"]["status"] == broker_status.value
    assert (
        execution.details["broker_result"]["client_request_id"]
        == broker.placed_orders[0].client_request_id
    )


def test_close_failure_keeps_position_open_and_flags_manual_review(
    session, broker, fixed_now
):
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
    service.process_price_update(
        INSTRUMENT,
        101.0,
        bid=100.9,
        ask=101.1,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now + timedelta(seconds=40),
    )

    executions = trade_service.list_executions(limit=10)
    intent = trade_service.list_trade_intents(limit=1)[0]
    position = trade_service.list_positions()[0]
    close_admissible = trade_service.find_close_admissible_trade_intent(
        strategy_name=STRATEGY,
        instrument=INSTRUMENT,
        broker_reference=position.broker_reference,
        position_id=position.id,
    )

    assert len(trade_service.list_positions()) == 1
    assert len(trade_service.list_trades()) == 0
    assert intent.state == TradeIntentState.CLOSE_REQUESTED.value
    assert close_admissible is not None
    assert close_admissible.id == intent.id
    assert executions[0].status == ExecutionStatus.NEEDS_MANUAL_REVIEW.value
    assert executions[0].requires_manual_review is True


def test_partial_close_result_moves_execution_to_manual_review(
    session, broker, fixed_now
):
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
    service.process_price_update(
        INSTRUMENT,
        101.0,
        bid=100.99,
        ask=101.01,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now + timedelta(seconds=40),
    )

    executions = trade_service.list_executions(limit=10)
    intent = trade_service.list_trade_intents(limit=1)[0]
    position = trade_service.list_positions()[0]
    close_admissible = trade_service.find_close_admissible_trade_intent(
        strategy_name=STRATEGY,
        instrument=INSTRUMENT,
        broker_reference=position.broker_reference,
        position_id=position.id,
    )

    assert len(trade_service.list_positions()) == 1
    assert len(trade_service.list_trades()) == 0
    assert intent.state == TradeIntentState.CLOSE_REQUESTED.value
    assert close_admissible is not None
    assert close_admissible.id == intent.id
    assert executions[0].status == ExecutionStatus.NEEDS_MANUAL_REVIEW.value
    assert executions[0].requires_manual_review is True
    assert executions[0].phase == ExecutionPhase.CLOSE.value
    assert executions[0].filled_size == 0.1
    assert executions[0].average_fill_price == 101.0


@pytest.mark.parametrize(
    ("close_status", "reason"),
    [
        (BrokerOrderStatus.REJECTED, "Broker rejected close."),
        (BrokerOrderStatus.AMBIGUOUS, "Close confirmation is ambiguous."),
    ],
)
def test_audit_life_002_incomplete_close_preserves_close_admissible_intent(
    session, broker, fixed_now, close_status, reason
):
    service = StrategyService(session)
    trade_service = TradeService(session)
    service.start_strategy(STRATEGY, INSTRUMENT)
    broker.place_order_outcomes.append(
        make_order_result(
            broker_reference="entry-close-admissible",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.5,
            executed_at=fixed_now + timedelta(seconds=1),
        )
    )
    broker.close_position_outcomes.append(
        BrokerOrderResult(
            broker_reference=f"close-{close_status.value.lower()}",
            instrument=INSTRUMENT,
            direction=OrderDirection.SELL,
            size=0.2,
            price=101.0,
            executed_at=fixed_now + timedelta(seconds=40),
            status=close_status,
            submitted_at=fixed_now + timedelta(seconds=40),
            acknowledged_at=fixed_now + timedelta(seconds=40),
            reason=reason,
            requires_manual_review=True,
        )
    )

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
    service.process_price_update(
        INSTRUMENT,
        101.0,
        bid=100.99,
        ask=101.01,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now + timedelta(seconds=40),
    )

    intent = trade_service.list_trade_intents(limit=1)[0]
    execution = trade_service.list_executions(limit=1)[0]
    position = trade_service.list_positions()[0]
    close_admissible = trade_service.find_close_admissible_trade_intent(
        strategy_name=STRATEGY,
        instrument=INSTRUMENT,
        broker_reference=position.broker_reference,
        position_id=position.id,
    )

    assert len(trade_service.list_trades()) == 0
    assert intent.state == TradeIntentState.CLOSE_REQUESTED.value
    assert close_admissible is not None
    assert close_admissible.id == intent.id
    assert execution.status == ExecutionStatus.NEEDS_MANUAL_REVIEW.value
    assert execution.requires_manual_review is True


def test_partial_entry_fill_keeps_position_but_restricts_runtime(
    session, broker, fixed_now
):
    service = StrategyService(session)
    trade_service = TradeService(session)
    service.start_strategy(STRATEGY, INSTRUMENT)
    broker.place_order_outcomes.append(
        BrokerOrderResult(
            broker_reference="entry-partial-1",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.5,
            executed_at=fixed_now + timedelta(seconds=1),
            status=BrokerOrderStatus.PARTIALLY_FILLED,
            filled_size=0.1,
            average_fill_price=100.5,
            submitted_at=fixed_now + timedelta(seconds=1),
            acknowledged_at=fixed_now + timedelta(seconds=1),
            requires_manual_review=True,
        )
    )

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

    intent = trade_service.list_trade_intents(limit=1)[0]
    execution = trade_service.list_executions(limit=1)[0]
    runtime = session.exec(
        select(StrategyRuntimeState)
        .where(StrategyRuntimeState.strategy_name == STRATEGY)
        .where(StrategyRuntimeState.instrument == INSTRUMENT)
    ).one()

    assert len(trade_service.list_positions()) == 1
    assert intent.state == TradeIntentState.PARTIALLY_FILLED.value
    assert intent.position_id is not None
    assert execution.status == ExecutionStatus.NEEDS_MANUAL_REVIEW.value
    assert execution.requires_manual_review is True
    assert execution.local_position_id == intent.position_id
    assert runtime.runtime_mode == "EXITS_ONLY"
    assert runtime_manager.get_engine(STRATEGY, INSTRUMENT).runtime_mode == "EXITS_ONLY"


def test_exits_only_runtime_mode_suppresses_new_entries(session, broker, fixed_now):
    service = StrategyService(session)
    trade_service = TradeService(session)
    service.start_strategy(STRATEGY, INSTRUMENT)
    service.set_runtime_mode(
        strategy_name=STRATEGY, instrument=INSTRUMENT, runtime_mode="EXITS_ONLY"
    )

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
        101.0,
        bid=100.99,
        ask=101.01,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now + timedelta(seconds=1),
    )

    runtime = session.exec(
        select(StrategyRuntimeState)
        .where(StrategyRuntimeState.strategy_name == STRATEGY)
        .where(StrategyRuntimeState.instrument == INSTRUMENT)
    ).one()
    assert runtime.runtime_mode == "EXITS_ONLY"
    assert broker.placed_orders == []
    assert trade_service.list_trade_intents(limit=10) == []


def test_audit_life_004_set_runtime_mode_preserves_manual_runtime_ownership(
    session,
):
    service = StrategyService(session)
    service.start_strategy(STRATEGY, INSTRUMENT, control_mode="MANUAL")

    service.set_runtime_mode(
        strategy_name=STRATEGY, instrument=INSTRUMENT, runtime_mode="EXITS_ONLY"
    )

    runtime = session.exec(
        select(StrategyRuntimeState)
        .where(StrategyRuntimeState.strategy_name == STRATEGY)
        .where(StrategyRuntimeState.instrument == INSTRUMENT)
    ).one()
    assert runtime.control_mode == "MANUAL"
    assert runtime.runtime_mode == "EXITS_ONLY"


def test_exits_only_runtime_mode_still_allows_strategy_driven_exits(
    session, broker, fixed_now
):
    service = StrategyService(session)
    trade_service = TradeService(session)
    broker.account_summary = BrokerAccountSummary(
        account_id="exits-only-flow",
        balance=101.0,
        available=101.0,
        profit_loss=0.0,
        equity=101.0,
        account_type=AccountType.DEMO,
    )
    service.start_strategy(STRATEGY, INSTRUMENT)
    broker.place_order_outcomes.append(
        make_order_result(
            broker_reference="entry-exits-only",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=101.0,
            average_fill_price=101.0,
            executed_at=fixed_now + timedelta(seconds=1),
        )
    )
    broker.close_position_outcomes.append(
        make_order_result(
            broker_reference="close-exits-only",
            instrument=INSTRUMENT,
            direction=OrderDirection.SELL,
            size=0.2,
            price=103.0,
            average_fill_price=103.0,
            executed_at=fixed_now + timedelta(seconds=40),
        )
    )

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
        101.0,
        bid=100.99,
        ask=101.01,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now + timedelta(seconds=1),
    )

    assert len(trade_service.list_positions()) == 1

    service.set_runtime_mode(
        strategy_name=STRATEGY, instrument=INSTRUMENT, runtime_mode="EXITS_ONLY"
    )
    service.process_price_update(
        INSTRUMENT,
        103.0,
        bid=102.8,
        ask=103.2,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now + timedelta(seconds=40),
    )

    runtime = session.exec(
        select(StrategyRuntimeState)
        .where(StrategyRuntimeState.strategy_name == STRATEGY)
        .where(StrategyRuntimeState.instrument == INSTRUMENT)
    ).one()
    trades = trade_service.list_trades()

    assert runtime.runtime_mode == "EXITS_ONLY"
    assert len(trade_service.list_positions()) == 0
    assert len(trades) == 1
    assert trades[0].close_broker_reference == "close-exits-only"


def test_mode_flip_to_exits_only_after_decision_admission_blocks_submission(
    session, broker, fixed_now
):
    service = StrategyService(session)
    trade_service = TradeService(session)
    broker.account_summary = BrokerAccountSummary(
        account_id="late-mode-flip",
        balance=101.0,
        available=101.0,
        profit_loss=0.0,
        equity=101.0,
        account_type=AccountType.DEMO,
    )
    service.start_strategy(STRATEGY, INSTRUMENT)
    service.evaluate_price_update(
        INSTRUMENT,
        100.0,
        bid=99.99,
        ask=100.01,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now,
    )
    candidates = service.evaluate_price_update(
        INSTRUMENT,
        101.0,
        bid=100.99,
        ask=101.01,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now + timedelta(seconds=1),
    )

    decisions = service.decide_signal_candidates(
        candidates, received_at=fixed_now + timedelta(seconds=1)
    )
    assert decisions[0].admitted is True

    service.set_runtime_mode(
        strategy_name=STRATEGY, instrument=INSTRUMENT, runtime_mode="EXITS_ONLY"
    )
    service.orchestrate_trade_decisions(
        decisions,
        price=101.0,
        bid=100.99,
        ask=101.01,
        received_at=fixed_now + timedelta(seconds=1),
    )

    intent = trade_service.list_trade_intents(limit=10)[0]
    assert broker.placed_orders == []
    assert trade_service.list_executions(limit=10) == []
    assert intent.state == TradeIntentState.FAILED.value
    assert intent.decision_reason_code == "entry_execution_blocked_runtime_mode_changed"


def test_execute_entry_signal_refuses_when_runtime_mode_is_exits_only(
    session, broker, fixed_now
):
    trade_service = TradeService(session)
    intent = trade_service.create_trade_intent(
        TradeIntent(
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            direction="BUY",
            state=TradeIntentState.APPROVED.value,
            signal_time=fixed_now,
            proposed_size=0.2,
            allocated_size=0.2,
            proposed_risk_percent=0.1,
            allocated_risk_percent=0.1,
        )
    )
    execution = trade_service.create_execution(
        Execution(
            trade_intent_id=intent.id,
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            phase=ExecutionPhase.ENTRY.value,
            status=ExecutionStatus.SUBMISSION_PENDING.value,
            client_request_id="ent-exits-only-block",
            signal_time=fixed_now,
            requested_size=0.2,
            requested_price=100.0,
        )
    )
    signal = EntrySignal(
        kind=SignalKind.ENTRY,
        strategy_name=STRATEGY,
        instrument=INSTRUMENT,
        observed_price=100.0,
        signal_at=fixed_now,
        direction=OrderDirection.BUY,
        size=0.2,
        risk_percent=0.1,
        bid=99.9,
        ask=100.1,
        market_status="TRADEABLE",
        tradable=True,
    )
    service = StrategyService(session)
    service.start_strategy(STRATEGY, INSTRUMENT)
    engine = runtime_manager.get_engine(STRATEGY, INSTRUMENT)
    assert engine is not None
    service.set_runtime_mode(
        strategy_name=STRATEGY, instrument=INSTRUMENT, runtime_mode="EXITS_ONLY"
    )

    with pytest.raises(ValueError, match="runtime mode is EXITS_ONLY"):
        StrategyService._execute_entry_signal(
            engine=engine,
            signal=signal,
            intent=intent,
            trade_service=trade_service,
            execution=execution,
        )

    refreshed_intent = trade_service.get_trade_intent(intent.id)
    refreshed_execution = trade_service.get_latest_execution_for_trade_intent(intent.id)
    assert broker.placed_orders == []
    assert (
        refreshed_intent is not None
        and refreshed_intent.decision_reason_code
        == "entry_execution_blocked_runtime_mode_changed"
    )
    assert (
        refreshed_execution is not None
        and refreshed_execution.status == ExecutionStatus.FAILED.value
    )


def test_execute_entry_signal_refuses_when_operational_entry_policy_is_false(
    session, broker, fixed_now, monkeypatch
):
    now = datetime.now(UTC)
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
    monkeypatch.setattr(
        "app.services.operational_state_service.get_operational_streaming_service",
        lambda: stub,
    )

    trade_service = TradeService(session)
    intent = trade_service.create_trade_intent(
        TradeIntent(
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            direction="BUY",
            state=TradeIntentState.APPROVED.value,
            signal_time=fixed_now,
            proposed_size=0.2,
            allocated_size=0.2,
            proposed_risk_percent=0.1,
            allocated_risk_percent=0.1,
        )
    )
    execution = trade_service.create_execution(
        Execution(
            trade_intent_id=intent.id,
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            phase=ExecutionPhase.ENTRY.value,
            status=ExecutionStatus.SUBMISSION_PENDING.value,
            client_request_id="ent-operational-block",
            signal_time=fixed_now,
            requested_size=0.2,
            requested_price=100.0,
        )
    )
    signal = EntrySignal(
        kind=SignalKind.ENTRY,
        strategy_name=STRATEGY,
        instrument=INSTRUMENT,
        observed_price=100.0,
        signal_at=fixed_now,
        direction=OrderDirection.BUY,
        size=0.2,
        risk_percent=0.1,
        bid=99.9,
        ask=100.1,
        market_status="TRADEABLE",
        tradable=True,
    )
    service = StrategyService(session)
    service.start_strategy(STRATEGY, INSTRUMENT)
    engine = runtime_manager.get_engine(STRATEGY, INSTRUMENT)
    assert engine is not None

    with pytest.raises(ValueError, match="operational policy"):
        StrategyService._execute_entry_signal(
            engine=engine,
            signal=signal,
            intent=intent,
            trade_service=trade_service,
            execution=execution,
        )

    refreshed_intent = trade_service.get_trade_intent(intent.id)
    refreshed_execution = trade_service.get_latest_execution_for_trade_intent(intent.id)
    assert broker.placed_orders == []
    assert (
        refreshed_intent is not None
        and refreshed_intent.decision_reason_code
        == "entry_execution_blocked_operational_policy"
    )
    assert (
        refreshed_execution is not None
        and refreshed_execution.status == ExecutionStatus.FAILED.value
    )


def test_start_strategy_uses_persisted_exits_only_mode_by_default(session):
    session.add(
        StrategyRuntimeState(
            runtime_id="persisted-exits-only-runtime",
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            status="STOPPED",
            recovery_state="PAUSED",
            runtime_mode="EXITS_ONLY",
        )
    )
    session.commit()

    service = StrategyService(session)
    service.start_strategy(STRATEGY, INSTRUMENT)

    engine = runtime_manager.get_engine(STRATEGY, INSTRUMENT)
    runtime = session.exec(
        select(StrategyRuntimeState)
        .where(StrategyRuntimeState.strategy_name == STRATEGY)
        .where(StrategyRuntimeState.instrument == INSTRUMENT)
    ).one()
    assert engine is not None
    assert engine.runtime_mode == "EXITS_ONLY"
    assert runtime.runtime_mode == "EXITS_ONLY"


def test_start_strategy_blocks_normal_restart_when_open_risk_is_unmanaged(session):
    session.add(
        StrategyDeployment(
            strategy_name=STRATEGY,
            deployment_key=f"{STRATEGY}:auto",
            state="BLOCKED",
            open_risk_management_state="UNMANAGED_OPEN_RISK",
        )
    )
    session.commit()

    with pytest.raises(ValueError, match="UNMANAGED_OPEN_RISK"):
        StrategyService(session).start_strategy(STRATEGY, INSTRUMENT)


def test_open_pnl_and_mark_price_helpers_use_directional_pricing():
    assert (
        StrategyService._mark_price(direction="BUY", price=100.0, bid=99.8, ask=100.2)
        == 99.8
    )
    assert (
        StrategyService._mark_price(direction="SELL", price=100.0, bid=99.8, ask=100.2)
        == 100.2
    )
    assert (
        StrategyService._calculate_open_pnl(
            direction="BUY", open_price=100.0, current_price=101.5, size=2.0
        )
        == 3.0
    )
    assert (
        StrategyService._calculate_open_pnl(
            direction="SELL", open_price=100.0, current_price=98.5, size=2.0
        )
        == 3.0
    )
