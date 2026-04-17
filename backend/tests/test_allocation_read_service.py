from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from app.core.broker import (
    AccountType,
    BrokerAccountSummary,
    BrokerMarketDetails,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerSizingMode,
    OrderDirection,
)
from app.core.config import get_settings
from app.core.runtime import runtime_manager
from app.core.signals import EntrySignal, SignalCandidate, SignalKind
from app.models.trade import Position, TradeIntentState
from app.services.allocation_alert_service import AllocationAlertService
from app.services.allocation_read_service import AllocationReadService
from app.services.capital_allocator_service import CapitalAllocatorService
from app.services.strategy_service import StrategyService
from app.services.trade_decision_service import TradeDecisionService
from app.services.trade_service import TradeService
from tests.fakes import make_order_result


INSTRUMENT = "CS.D.EURUSD.MINI.IP"


def _candidate(
    *,
    strategy_name: str,
    instrument: str,
    direction: OrderDirection,
    signal_at,
    broker,
    price: float = 1.1001,
    confidence: float = 0.8,
    risk_per_trade: float = 0.4,
    family_name: str | None = None,
    stop_loss_price: float | None = None,
    sizing_profile: dict[str, object] | None = None,
) -> SignalCandidate:
    broker.market_details_by_instrument.setdefault(
        instrument,
        BrokerMarketDetails(
            instrument=instrument,
            name=instrument,
            bid=price - 0.0001,
            offer=price + 0.0001,
            high=price + 0.001,
            low=price - 0.001,
            percentage_change=0.0,
            net_change=0.0,
            market_status="TRADEABLE",
            update_time=signal_at.isoformat(),
            tradable=True,
            min_deal_size=0.1,
            size_step=0.1,
            base_currency="EUR",
            quote_currency="USD",
            metadata={
                "sizing_profile": sizing_profile
                or {
                    "mode": BrokerSizingMode.EXACT_POINT_VALUE.value,
                    "price_increment": 0.0001,
                    "value_per_increment": 1.0,
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
            signal_at=signal_at,
            direction=direction,
            size=0.0,
            risk_percent=risk_per_trade,
            stop_loss_price=stop_loss_price,
            bid=price - 0.0001,
            ask=price + 0.0001,
            market_status="TRADEABLE",
            tradable=True,
        ),
        engine=SimpleNamespace(strategy=SimpleNamespace(name=strategy_name), broker=broker, instrument=instrument),
        source_tier="TIER1",
        confidence=confidence,
        metadata=SimpleNamespace(
            family_name=family_name or strategy_name,
        ),
    )


def test_allocation_cycle_summary_is_queryable(session, broker, fixed_now):
    broker.account_summary = BrokerAccountSummary(
        account_id="alloc-cycle",
        balance=10_000.0,
        available=10_000.0,
        profit_loss=0.0,
        equity=10_000.0,
        account_type=AccountType.DEMO,
    )
    decisions = CapitalAllocatorService(session).allocate(
        [
            _candidate(
                strategy_name="breakout_guard",
                instrument="CS.D.EURUSD.MINI.IP",
                direction=OrderDirection.BUY,
                signal_at=fixed_now,
                broker=broker,
                stop_loss_price=1.0990,
            ),
            _candidate(
                strategy_name="mean_reversion",
                instrument="CS.D.EURUSD.MINI.IP",
                direction=OrderDirection.SELL,
                signal_at=fixed_now,
                broker=broker,
                confidence=0.3,
                stop_loss_price=1.1012,
            ),
        ],
        received_at=fixed_now,
    )

    cycles = AllocationReadService(session).list_recent_cycles(limit=5)

    assert len(cycles) == 1
    assert cycles[0]["candidate_count"] == 2
    assert cycles[0]["approved_count"] == 1
    assert cycles[0]["blocked_conflict_count"] == 1
    assert cycles[0]["cycle_id"] == decisions[0].cycle_id


def test_allocation_read_service_shows_hard_risk_rejection_after_allocator_approval(session, broker, fixed_now):
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    broker.account_summary = BrokerAccountSummary(
        account_id="hard-risk",
        balance=10_000.0,
        available=10_000.0,
        profit_loss=0.0,
        equity=10_000.0,
        account_type=AccountType.DEMO,
    )
    get_settings().runtime_global_entry_kill_switch = True

    result = TradeDecisionService(session).decide_signal_candidates(
        [
            _candidate(
                strategy_name="smoke_test_hold",
                instrument=INSTRUMENT,
                direction=OrderDirection.BUY,
                signal_at=fixed_now,
                broker=broker,
                risk_per_trade=0.5,
                stop_loss_price=1.0990,
            )
        ],
        received_at=fixed_now,
    )[0]

    intent_view = AllocationReadService(session).get_intent(result.intent.id or 0)

    assert result.admitted is False
    assert intent_view is not None
    assert intent_view["allocation_outcome"]["stage"] == "hard_risk_rejected"
    assert intent_view["allocation_outcome"]["allocator_selected"] is True
    assert intent_view["allocation_outcome"]["hard_risk_blocked"] is True


def test_risk_tracking_progresses_from_estimated_to_fill_derived(session, broker, fixed_now):
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    broker.account_summary = BrokerAccountSummary(
        account_id="risk-track",
        balance=100_000.0,
        available=100_000.0,
        profit_loss=0.0,
        equity=100_000.0,
        account_type=AccountType.DEMO,
    )
    broker.market_details_by_instrument[INSTRUMENT] = BrokerMarketDetails(
        instrument=INSTRUMENT,
        name=INSTRUMENT,
        bid=100.99,
        offer=101.01,
        high=102.0,
        low=99.0,
        percentage_change=0.0,
        net_change=0.0,
        market_status="TRADEABLE",
        update_time=fixed_now.isoformat(),
        tradable=True,
        min_deal_size=0.0001,
        size_step=0.0001,
        base_currency="EUR",
        quote_currency="USD",
        metadata={
            "sizing_profile": {
                "mode": BrokerSizingMode.EXACT_POINT_VALUE.value,
                "price_increment": 0.0001,
                "value_per_increment": 1.0,
            }
        },
    )
    service = StrategyService(session)
    service.start_strategy("smoke_test_hold", INSTRUMENT)
    broker.place_order_outcomes.append(
        make_order_result(
            broker_reference="entry-risk-1",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=101.0,
            average_fill_price=101.25,
            executed_at=fixed_now + timedelta(seconds=1),
        )
    )

    service.process_price_update(INSTRUMENT, 100.0, bid=99.99, ask=100.01, market_status="TRADEABLE", tradable=True, received_at=fixed_now)
    service.process_price_update(INSTRUMENT, 101.0, bid=100.99, ask=101.01, market_status="TRADEABLE", tradable=True, received_at=fixed_now + timedelta(seconds=1))
    service.process_price_update(INSTRUMENT, 101.0, bid=100.99, ask=101.01, market_status="TRADEABLE", tradable=True, received_at=fixed_now + timedelta(seconds=1))

    intent = TradeService(session).list_trade_intents(limit=1)[0]
    intent_view = AllocationReadService(session).get_intent(intent.id or 0)

    assert intent.state == TradeIntentState.POSITION_OPENED.value
    assert intent_view["risk_tracking"]["estimated_allocation_risk_amount"] is not None
    assert intent_view["risk_tracking"]["submitted_executable_risk_amount"] is not None
    assert intent_view["risk_tracking"]["fill_derived_risk_amount"] is not None
    assert intent_view["risk_tracking"]["risk_state"] == "filled"
    assert intent_view["position"]["entry_risk_amount"] == intent_view["risk_tracking"]["fill_derived_risk_amount"]
    assert intent_view["risk_truth_confidence"] == "EXACT_FILL_DERIVED"
    assert intent_view["latest_execution"]["risk_truth_confidence"] == "EXACT_FILL_DERIVED"
    assert intent_view["position"]["risk_truth_confidence"] == "EXACT_FILL_DERIVED"
    assert intent_view["risk_reconciliation"]["estimated"]["risk_amount"] is not None
    assert intent_view["risk_reconciliation"]["submitted"]["risk_amount"] is not None
    assert intent_view["risk_reconciliation"]["filled"]["risk_amount"] is not None
    assert intent_view["risk_reconciliation"]["live_position"]["risk_amount"] == intent_view["position"]["entry_risk_amount"]
    assert intent_view["risk_reconciliation"]["filled"]["risk_truth_confidence"] == "EXACT_FILL_DERIVED"


def test_execution_revalidation_failure_is_visible_to_operator_read_model(session, broker, fixed_now):
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    trade_service = TradeService(session)
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
        metadata={
            "sizing_profile": {
                "mode": BrokerSizingMode.EXACT_POINT_VALUE.value,
                "price_increment": 0.0001,
                "value_per_increment": 1.0,
            }
        },
    )
    decision = TradeDecisionService(session).decide_signal_candidates(
        [
            _candidate(
                strategy_name="smoke_test_hold",
                instrument=INSTRUMENT,
                direction=OrderDirection.BUY,
                signal_at=fixed_now,
                broker=broker,
                price=100.0,
                risk_per_trade=0.1,
                stop_loss_price=99.999,
            )
        ],
        received_at=fixed_now,
    )[0]
    trade_service.transition_trade_intent(
        decision.intent,
        state=TradeIntentState.APPROVED,
        allocated_size=0.23,
    )
    execution, _ = StrategyService._prepare_execution(
        trade_service=trade_service,
        trade_intent_id=decision.intent.id,
        strategy_name="smoke_test_hold",
        instrument=INSTRUMENT,
        phase="ENTRY",
        signal_time=fixed_now,
        requested_size=decision.intent.allocated_size,
        requested_price=100.0,
        reason="Execution attempt created for approved entry intent",
        details={"action_key": f"entry:smoke_test_hold:{INSTRUMENT}:BUY"},
    )
    engine = runtime_manager.start(strategy_name="smoke_test_hold", instrument=INSTRUMENT)

    try:
        StrategyService._execute_entry_signal(
            engine=engine,
            signal=EntrySignal(
                kind=SignalKind.ENTRY,
                strategy_name="smoke_test_hold",
                instrument=INSTRUMENT,
                observed_price=100.0,
                signal_at=fixed_now,
                direction=OrderDirection.BUY,
                size=decision.intent.allocated_size or 0.0,
                risk_percent=decision.intent.allocated_risk_percent or 0.0,
                bid=99.9,
                ask=100.1,
                market_status="TRADEABLE",
                tradable=True,
            ),
            intent=decision.intent,
            trade_service=trade_service,
            execution=execution,
        )
    except Exception:
        pass

    intent_view = AllocationReadService(session).get_intent(decision.intent.id or 0)

    assert intent_view["allocation_outcome"]["stage"] == "execution_revalidation_failed"
    assert intent_view["latest_execution"]["status"] == "FAILED"
    assert intent_view["latest_execution"]["details"]["execution_revalidation"]["reallocation_required"] is True


def test_drift_summary_and_alerts_surface_material_execution_drift(session, broker, fixed_now):
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    broker.account_summary = BrokerAccountSummary(
        account_id="drift-alert",
        balance=10_000.0,
        available=10_000.0,
        profit_loss=0.0,
        equity=10_000.0,
        account_type=AccountType.DEMO,
    )
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
        update_time=fixed_now.isoformat(),
        tradable=True,
        min_deal_size=0.1,
        size_step=0.1,
        base_currency="EUR",
        quote_currency="USD",
        metadata={
            "sizing_profile": {
                "mode": BrokerSizingMode.APPROXIMATE_PRICE_DELTA.value,
                "contract_multiplier": 1.0,
            }
        },
    )
    service = StrategyService(session)
    service.start_strategy("smoke_test_hold", INSTRUMENT)
    broker.place_order_outcomes.append(
        make_order_result(
            broker_reference="entry-drift-1",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=6.9,
            price=100.0,
            average_fill_price=120.0,
            executed_at=fixed_now + timedelta(seconds=1),
        )
    )

    service.process_price_update(INSTRUMENT, 100.0, bid=99.99, ask=100.01, market_status="TRADEABLE", tradable=True, received_at=fixed_now)
    service.process_price_update(INSTRUMENT, 101.0, bid=100.99, ask=101.01, market_status="TRADEABLE", tradable=True, received_at=fixed_now + timedelta(seconds=1))

    read_service = AllocationReadService(session)
    drift = read_service.get_drift_summary(window_minutes=240)
    alerts = read_service.list_alerts(window_minutes=240)
    intent = TradeService(session).list_trade_intents(limit=1)[0]
    intent_view = read_service.get_intent(intent.id or 0)

    assert drift["material_drift_count"] >= 1
    assert drift["worst_intents"][0]["trade_intent_id"] == intent.id
    assert intent_view["risk_reconciliation"]["flags"]["material_execution_drift"] is True
    assert any(alert["alert_type"] == "material_execution_drift" for alert in alerts)


def test_alerts_surface_degraded_cycles_and_revalidation_failures(session, broker, fixed_now):
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    get_settings().allocation_alert_revalidation_failure_threshold = 1
    broker._account_type = AccountType.LIVE
    broker.account_summary = BrokerAccountSummary(
        account_id="live-alerts",
        balance=10_000.0,
        available=10_000.0,
        profit_loss=0.0,
        equity=10_000.0,
        account_type=AccountType.LIVE,
    )
    broker.market_details_by_instrument[INSTRUMENT] = BrokerMarketDetails(
        instrument=INSTRUMENT,
        name=INSTRUMENT,
        bid=1.1,
        offer=1.1002,
        high=1.11,
        low=1.09,
        percentage_change=0.0,
        net_change=0.0,
        market_status="TRADEABLE",
        update_time=fixed_now.isoformat(),
        tradable=True,
        min_deal_size=0.1,
        size_step=0.1,
        base_currency="EUR",
        quote_currency="USD",
        metadata={
            "sizing_profile": {
                "mode": BrokerSizingMode.APPROXIMATE_PRICE_DELTA.value,
                "contract_multiplier": 1.0,
            }
        },
    )
    CapitalAllocatorService(session).allocate(
        [
            _candidate(
                strategy_name="live_blocked",
                instrument=INSTRUMENT,
                direction=OrderDirection.BUY,
                signal_at=fixed_now,
                broker=broker,
                stop_loss_price=1.095,
                sizing_profile={
                    "mode": BrokerSizingMode.APPROXIMATE_PRICE_DELTA.value,
                    "contract_multiplier": 1.0,
                },
            )
        ],
        received_at=fixed_now,
    )

    broker._account_type = AccountType.DEMO
    decision = TradeDecisionService(session).decide_signal_candidates(
        [
            _candidate(
                strategy_name="revalidation_test",
                instrument=INSTRUMENT,
                direction=OrderDirection.BUY,
                signal_at=fixed_now + timedelta(seconds=5),
                broker=broker,
                price=100.0,
                risk_per_trade=0.1,
                stop_loss_price=99.999,
            )
        ],
        received_at=fixed_now + timedelta(seconds=5),
    )[0]
    TradeService(session).transition_trade_intent(decision.intent, state=TradeIntentState.APPROVED, allocated_size=0.23)
    execution, _ = StrategyService._prepare_execution(
        trade_service=TradeService(session),
        trade_intent_id=decision.intent.id,
        strategy_name="revalidation_test",
        instrument=INSTRUMENT,
        phase="ENTRY",
        signal_time=fixed_now + timedelta(seconds=5),
        requested_size=decision.intent.allocated_size,
        requested_price=100.0,
        reason="Execution attempt created for approved entry intent",
        details={"action_key": f"entry:revalidation_test:{INSTRUMENT}:BUY"},
    )
    engine = runtime_manager.start(strategy_name="smoke_test_hold", instrument=INSTRUMENT)
    try:
        StrategyService._execute_entry_signal(
            engine=engine,
            signal=EntrySignal(
                kind=SignalKind.ENTRY,
                strategy_name="revalidation_test",
                instrument=INSTRUMENT,
                observed_price=100.0,
                signal_at=fixed_now + timedelta(seconds=5),
                direction=OrderDirection.BUY,
                size=decision.intent.allocated_size or 0.0,
                risk_percent=decision.intent.allocated_risk_percent or 0.0,
                bid=99.9,
                ask=100.1,
                market_status="TRADEABLE",
                tradable=True,
            ),
            intent=decision.intent,
            trade_service=TradeService(session),
            execution=execution,
        )
    except Exception:
        pass

    alerts = AllocationReadService(session).list_alerts(window_minutes=240)

    assert any(alert["alert_type"] == "degraded_allocation_cycles" for alert in alerts)
    assert any(alert["alert_type"] == "repeated_execution_revalidation_failures" for alert in alerts)


def test_exposure_summary_separates_reserved_and_live_risk(session, broker, fixed_now):
    broker.account_summary = BrokerAccountSummary(
        account_id="exposure",
        balance=10_000.0,
        available=10_000.0,
        profit_loss=0.0,
        equity=10_000.0,
        account_type=AccountType.DEMO,
    )
    decision = TradeDecisionService(session).decide_signal_candidates(
        [
            _candidate(
                strategy_name="reserve_only",
                instrument="CS.D.EURUSD.MINI.IP",
                direction=OrderDirection.BUY,
                signal_at=fixed_now,
                broker=broker,
                family_name="trend",
                stop_loss_price=1.0990,
            )
        ],
        received_at=fixed_now,
    )[0]
    trade_service = TradeService(session)
    trade_service.transition_trade_intent(
        decision.intent,
        state=TradeIntentState.APPROVED,
        submitted_risk_amount=decision.intent.estimated_risk_amount,
    )
    trade_service.record_broker_position(
        Position(
            trade_intent_id=None,
            strategy_name="live_only",
            family_name="carry",
            broker_reference="live-pos-1",
            instrument="CS.D.GBPUSD.MINI.IP",
            direction="BUY",
            size=1.0,
            open_price=1.25,
            open_time=fixed_now,
            risk_percent=0.75,
            entry_risk_amount=75.0,
            account_type=AccountType.DEMO.value,
            is_open=True,
        )
    )

    summary = AllocationReadService(session).get_exposure_summary()

    assert summary["totals"]["reserved_risk_percent"] > 0
    assert summary["totals"]["live_risk_percent"] == 0.75
    assert any(bucket["name"] == "trend" for bucket in summary["by_family"])
    assert any(bucket["name"] == "carry" for bucket in summary["by_family"])


def test_partial_fill_is_marked_provisional_and_updates_exposure(session, broker, fixed_now):
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    broker.account_summary = BrokerAccountSummary(
        account_id="partial-fill",
        balance=10_000.0,
        available=10_000.0,
        profit_loss=0.0,
        equity=10_000.0,
        account_type=AccountType.DEMO,
    )
    service = StrategyService(session)
    service.start_strategy("smoke_test_hold", INSTRUMENT)
    broker.place_order_outcomes.append(
        BrokerOrderResult(
            broker_reference="entry-partial-1",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=101.0,
            executed_at=fixed_now + timedelta(seconds=1),
            status=BrokerOrderStatus.PARTIALLY_FILLED,
            filled_size=0.1,
            average_fill_price=101.1,
            submitted_at=fixed_now + timedelta(seconds=1),
            acknowledged_at=fixed_now + timedelta(seconds=1),
            requires_manual_review=True,
        )
    )
    service.process_price_update(INSTRUMENT, 100.0, bid=99.99, ask=100.01, market_status="TRADEABLE", tradable=True, received_at=fixed_now)
    service.process_price_update(INSTRUMENT, 101.0, bid=100.99, ask=101.01, market_status="TRADEABLE", tradable=True, received_at=fixed_now + timedelta(seconds=1))

    read_service = AllocationReadService(session)
    intent = TradeService(session).list_trade_intents(limit=1)[0]
    intent_view = read_service.get_intent(intent.id or 0)
    exposure = read_service.get_exposure_summary()
    alerts = read_service.list_alerts(window_minutes=240)

    assert intent_view["risk_truth_confidence"] == "PARTIAL_FILL_PROVISIONAL"
    assert intent_view["position"]["risk_truth_confidence"] == "PARTIAL_FILL_PROVISIONAL"
    assert intent_view["risk_reconciliation"]["flags"]["partial_fill_provisional"] is True
    assert intent_view["allocation_outcome"]["fill_status"] == TradeIntentState.PARTIALLY_FILLED.value
    assert exposure["totals"]["reserved_risk_percent"] == 0.0
    assert exposure["totals"]["provisional_live_risk_percent"] > 0.0
    assert any(alert["alert_type"] == "incomplete_fill_truth" for alert in alerts)


def test_alert_state_transitions_support_acknowledge_resolve_and_recurrence(session, broker, fixed_now):
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    broker.account_summary = BrokerAccountSummary(
        account_id="alert-recurrence",
        balance=10_000.0,
        available=10_000.0,
        profit_loss=0.0,
        equity=10_000.0,
        account_type=AccountType.DEMO,
    )
    get_settings().allocation_drift_warning_percent = 5.0
    service = StrategyService(session)
    service.start_strategy("smoke_test_hold", INSTRUMENT)
    broker.place_order_outcomes.append(
        make_order_result(
            broker_reference="entry-alert-1",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=6.9,
            price=100.0,
            average_fill_price=120.0,
            executed_at=fixed_now + timedelta(seconds=1),
        )
    )
    service.process_price_update(INSTRUMENT, 100.0, bid=99.99, ask=100.01, market_status="TRADEABLE", tradable=True, received_at=fixed_now)
    service.process_price_update(INSTRUMENT, 101.0, bid=100.99, ask=101.01, market_status="TRADEABLE", tradable=True, received_at=fixed_now + timedelta(seconds=1))

    alert_service = AllocationAlertService(session)
    alerts = alert_service.list_alerts(refresh=True, window_minutes=240)
    critical = next(alert for alert in alerts if alert.alert_type == "material_execution_drift")

    acknowledged = alert_service.acknowledge_alert(critical.id or 0, actor_id="test-operator")
    assert acknowledged is not None
    assert acknowledged.state == "ACKNOWLEDGED"

    resolved = alert_service.resolve_alert(critical.id or 0, actor_id="test-operator")
    assert resolved is not None
    assert resolved.state == "RESOLVED"

    reopened = alert_service.list_alerts(refresh=True, window_minutes=240)
    material = next(alert for alert in reopened if alert.alert_type == "material_execution_drift")
    assert material.state == "OPEN"
    assert material.recurrence_count >= 2


def test_directional_currency_exposure_tracks_net_bias(session, broker, fixed_now):
    broker.account_summary = BrokerAccountSummary(
        account_id="directional-exposure",
        balance=10_000.0,
        available=10_000.0,
        profit_loss=0.0,
        equity=10_000.0,
        account_type=AccountType.DEMO,
    )
    decisions = TradeDecisionService(session).decide_signal_candidates(
        [
            _candidate(
                strategy_name="eur_trend",
                instrument="CS.D.EURUSD.MINI.IP",
                direction=OrderDirection.BUY,
                signal_at=fixed_now,
                broker=broker,
                family_name="trend",
                stop_loss_price=1.0990,
            ),
            _candidate(
                strategy_name="gbp_trend",
                instrument="CS.D.GBPUSD.MINI.IP",
                direction=OrderDirection.BUY,
                signal_at=fixed_now + timedelta(seconds=1),
                broker=broker,
                family_name="trend",
                stop_loss_price=1.2490,
                price=1.25,
            ),
        ],
        received_at=fixed_now,
    )
    trade_service = TradeService(session)
    for result in decisions:
        trade_service.transition_trade_intent(
            result.intent,
            state=TradeIntentState.APPROVED,
            submitted_risk_amount=result.intent.estimated_risk_amount,
        )

    summary = AllocationReadService(session).get_exposure_summary()
    usd = next(bucket for bucket in summary["currency_directional"] if bucket["currency"] == "USD")

    assert usd["net_bias"] == "SHORT"
    assert usd["gross_risk_percent"] > 0.0
    assert usd["net_risk_percent"] < 0.0
