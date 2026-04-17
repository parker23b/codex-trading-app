from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.broker import AccountType, BrokerAccountSummary, BrokerMarketDetails, BrokerSizingMode, OrderDirection
from app.core.runtime import runtime_manager
from app.core.signals import EntrySignal, SignalCandidate, SignalKind
from app.models.trade import Position, TradeIntent, TradeIntentState
from app.services.capital_allocator_service import CapitalAllocatorService
from app.services.trade_decision_service import TradeDecisionService
from app.services.trade_service import TradeService
from tests.fakes import ContractRiskBroker


def _candidate(
    *,
    strategy_name: str,
    instrument: str,
    direction: OrderDirection,
    signal_at,
    broker,
    price: float,
    confidence: float = 0.7,
    risk_per_trade: float = 0.5,
    family_name: str | None = None,
    stop_loss_price: float | None = None,
    expected_reward_risk: float | None = None,
    size_step: float | None = None,
    min_deal_size: float | None = None,
    sizing_profile: dict[str, object] | None = None,
) -> SignalCandidate:
    broker.market_details_by_instrument.setdefault(
        instrument,
        BrokerMarketDetails(
            instrument=instrument,
            name=instrument,
            bid=price,
            offer=price,
            high=price + 1.0,
            low=price - 1.0,
            percentage_change=0.0,
            net_change=0.0,
            market_status="TRADEABLE",
            update_time=signal_at.isoformat(),
            tradable=True,
            min_deal_size=min_deal_size,
            size_step=size_step,
            base_currency="EUR" if instrument.startswith("CS.D.EURUSD") else None,
            quote_currency="USD" if instrument.startswith("CS.D.EURUSD") else None,
            metadata={"sizing_profile": sizing_profile or {"mode": BrokerSizingMode.APPROXIMATE_PRICE_DELTA.value, "contract_multiplier": 1.0}},
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
            risk_percent=0.0,
            stop_loss_price=stop_loss_price,
            expected_reward_risk=expected_reward_risk,
            bid=price,
            ask=price,
            market_status="TRADEABLE",
            tradable=True,
        ),
        engine=SimpleNamespace(strategy=SimpleNamespace(name=strategy_name), broker=broker, instrument=instrument),
        source_tier="TIER1",
        confidence=confidence,
        metadata=SimpleNamespace(
            risk_per_trade=risk_per_trade,
            family_name=family_name or strategy_name,
        ),
    )


def test_allocator_no_longer_contains_ig_specific_sizing_branch():
    source = Path("/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/capital_allocator_service.py").read_text()

    assert "ig_point_value" not in source


def test_allocator_sizes_with_broker_owned_exact_point_value_quote(session, broker, fixed_now):
    broker.account_summary = BrokerAccountSummary(
        account_id="ig-exact",
        balance=1_000.0,
        available=1_000.0,
        profit_loss=0.0,
        equity=1_000.0,
        account_type=AccountType.DEMO,
    )
    candidate = _candidate(
        strategy_name="fx_micro_pullback",
        instrument="CS.D.EURUSD.MINI.IP",
        direction=OrderDirection.BUY,
        signal_at=fixed_now,
        broker=broker,
        price=1.2000,
        risk_per_trade=1.0,
        stop_loss_price=1.1990,
        sizing_profile={
            "mode": BrokerSizingMode.EXACT_POINT_VALUE.value,
            "price_increment": 0.0001,
            "value_per_increment": 1.0,
        },
    )

    decision = CapitalAllocatorService(session).allocate([candidate], received_at=fixed_now)[0]

    assert decision.selected is True
    assert decision.sizing_method == "stop_distance"
    assert decision.risk_amount == pytest.approx(10.0)
    assert decision.normalized_size == pytest.approx(1.0)
    assert decision.sizing_details["sizing_mode"] == BrokerSizingMode.EXACT_POINT_VALUE.value
    assert decision.sizing_details["risk_per_unit"] == pytest.approx(10.0)


def test_allocator_uses_same_broker_quote_model_for_fallback_stop(session, broker, fixed_now):
    broker.account_summary = BrokerAccountSummary(
        account_id="ig-fallback",
        balance=1_000.0,
        available=1_000.0,
        profit_loss=0.0,
        equity=1_000.0,
        account_type=AccountType.DEMO,
    )
    candidate = _candidate(
        strategy_name="fx_micro_pullback",
        instrument="CS.D.EURUSD.MINI.IP",
        direction=OrderDirection.BUY,
        signal_at=fixed_now,
        broker=broker,
        price=1.2000,
        risk_per_trade=1.0,
        sizing_profile={
            "mode": BrokerSizingMode.EXACT_POINT_VALUE.value,
            "price_increment": 0.0001,
            "value_per_increment": 1.0,
        },
    )

    decision = CapitalAllocatorService(session).allocate([candidate], received_at=fixed_now)[0]

    assert decision.selected is True
    assert decision.sizing_method == "fallback_percent_stop"
    assert decision.sizing_details["sizing_mode"] == BrokerSizingMode.EXACT_POINT_VALUE.value
    assert decision.sizing_details["stop_distance_price"] == pytest.approx(0.006)
    assert decision.sizing_details["risk_per_unit"] == pytest.approx(60.0)
    assert decision.normalized_size == pytest.approx(10.0 / 60.0)


def test_allocator_supports_second_broker_with_exact_contract_risk_mode(session, fixed_now):
    broker = ContractRiskBroker(
        account_summary=BrokerAccountSummary(
            account_id="contract-broker",
            balance=5_000.0,
            available=5_000.0,
            profit_loss=0.0,
            equity=5_000.0,
            account_type=AccountType.DEMO,
        )
    )
    broker.contract_multipliers["FX.TEST"] = 100_000.0
    broker.market_details_by_instrument["FX.TEST"] = BrokerMarketDetails(
        instrument="FX.TEST",
        name="FX.TEST",
        bid=1.2500,
        offer=1.2500,
        high=1.26,
        low=1.24,
        percentage_change=0.0,
        net_change=0.0,
        market_status="TRADEABLE",
        update_time=fixed_now.isoformat(),
        tradable=True,
        min_deal_size=0.1,
        size_step=0.1,
        base_currency="EUR",
        quote_currency="USD",
    )
    candidate = _candidate(
        strategy_name="fx_contract_risk",
        instrument="FX.TEST",
        direction=OrderDirection.BUY,
        signal_at=fixed_now,
        broker=broker,
        price=1.2500,
        risk_per_trade=1.0,
        stop_loss_price=1.2490,
    )

    decision = CapitalAllocatorService(session).allocate([candidate], received_at=fixed_now)[0]

    assert decision.selected is True
    assert decision.sizing_details["sizing_mode"] == BrokerSizingMode.EXACT_CONTRACT_RISK.value
    assert decision.sizing_details["risk_per_unit"] == pytest.approx(100.0)
    assert decision.normalized_size == pytest.approx(0.5)


def test_allocator_reserves_budget_for_pending_intents_across_cycles(session, broker, fixed_now):
    broker.account_summary = BrokerAccountSummary(
        account_id="reserved-budget",
        balance=1_000.0,
        available=1_000.0,
        profit_loss=0.0,
        equity=1_000.0,
        account_type=AccountType.DEMO,
    )
    session.add(
        TradeIntent(
            strategy_name="breakout_guard",
            family_name="breakout",
            instrument="IX.D.NASDAQ.DAILY.IP",
            direction="BUY",
            state=TradeIntentState.APPROVED.value,
            signal_time=fixed_now,
            proposed_size=4.0,
            allocated_size=4.0,
            proposed_risk_percent=0.9,
            allocated_risk_percent=0.9,
            observed_price=100.0,
        )
    )
    session.commit()
    candidate = _candidate(
        strategy_name="mean_reversion",
        instrument="IX.D.FTSE.DAILY.IP",
        direction=OrderDirection.BUY,
        signal_at=fixed_now,
        broker=broker,
        price=100.0,
        risk_per_trade=0.5,
        stop_loss_price=99.0,
    )
    service = CapitalAllocatorService(session)
    service.settings.runtime_max_open_risk_percent = 1.0

    decision = service.allocate([candidate], received_at=fixed_now)[0]

    assert decision.selected is True
    assert decision.binding_budget == "portfolio_risk"
    assert decision.allocated_risk_percent == pytest.approx(0.1)


def test_allocator_rejects_when_account_equity_is_unavailable(session, broker, fixed_now, monkeypatch):
    monkeypatch.setattr(broker, "get_account_summary", lambda: (_ for _ in ()).throw(RuntimeError("broker down")))
    candidate = _candidate(
        strategy_name="mean_reversion",
        instrument="IX.D.FTSE.DAILY.IP",
        direction=OrderDirection.BUY,
        signal_at=fixed_now,
        broker=broker,
        price=100.0,
    )

    decision = CapitalAllocatorService(session).allocate([candidate], received_at=fixed_now)[0]

    assert decision.selected is False
    assert decision.reason_code == "account_equity_unavailable"


def test_allocator_rejects_when_account_equity_is_non_positive(session, broker, fixed_now):
    broker.account_summary = BrokerAccountSummary(
        account_id="invalid-equity",
        balance=0.0,
        available=0.0,
        profit_loss=0.0,
        equity=0.0,
        account_type=AccountType.DEMO,
    )
    candidate = _candidate(
        strategy_name="mean_reversion",
        instrument="IX.D.FTSE.DAILY.IP",
        direction=OrderDirection.BUY,
        signal_at=fixed_now,
        broker=broker,
        price=100.0,
    )

    decision = CapitalAllocatorService(session).allocate([candidate], received_at=fixed_now)[0]

    assert decision.selected is False
    assert decision.reason_code == "account_equity_invalid"


def test_allocator_handles_broker_metadata_failure_gracefully(session, broker, fixed_now, monkeypatch):
    broker.account_summary = BrokerAccountSummary(
        account_id="meta-fail",
        balance=1_000.0,
        available=1_000.0,
        profit_loss=0.0,
        equity=1_000.0,
        account_type=AccountType.DEMO,
    )
    monkeypatch.setattr(broker, "get_market_details", lambda instrument: (_ for _ in ()).throw(RuntimeError("metadata unavailable")))
    candidate = _candidate(
        strategy_name="mean_reversion",
        instrument="IX.D.FTSE.DAILY.IP",
        direction=OrderDirection.BUY,
        signal_at=fixed_now,
        broker=broker,
        price=100.0,
    )

    decision = CapitalAllocatorService(session).allocate([candidate], received_at=fixed_now)[0]

    assert decision.selected is False
    assert decision.reason_code == "broker_metadata_unavailable"


def test_allocator_rejects_approximate_broker_quote_for_live_account(session, broker, fixed_now):
    broker._account_type = AccountType.LIVE
    broker.account_summary = BrokerAccountSummary(
        account_id="live-approx",
        balance=1_000.0,
        available=1_000.0,
        profit_loss=0.0,
        equity=1_000.0,
        account_type=AccountType.LIVE,
    )
    candidate = _candidate(
        strategy_name="mean_reversion",
        instrument="IX.D.FTSE.DAILY.IP",
        direction=OrderDirection.BUY,
        signal_at=fixed_now,
        broker=broker,
        price=100.0,
        sizing_profile={"mode": BrokerSizingMode.APPROXIMATE_PRICE_DELTA.value, "contract_multiplier": 1.0},
    )

    decision = CapitalAllocatorService(session).allocate([candidate], received_at=fixed_now)[0]

    assert decision.selected is False
    assert decision.reason_code == "approximate_sizing_unsupported"


def test_family_budget_uses_persisted_family_values(session, broker, fixed_now):
    broker.account_summary = BrokerAccountSummary(
        account_id="family-budget",
        balance=1_000.0,
        available=1_000.0,
        profit_loss=0.0,
        equity=1_000.0,
        account_type=AccountType.DEMO,
    )
    session.add(
        Position(
            strategy_name="fx_micro_pullback",
            family_name="fx_pullback",
            broker_reference="fx-pos",
            instrument="CS.D.EURUSD.MINI.IP",
            direction="BUY",
            size=1.0,
            open_price=1.2000,
            open_time=fixed_now,
            risk_percent=1.4,
            account_type="DEMO",
            is_open=True,
        )
    )
    session.commit()
    candidate = _candidate(
        strategy_name="volatility_adjusted_pullback_continuation",
        instrument="CS.D.GBPUSD.MINI.IP",
        direction=OrderDirection.BUY,
        signal_at=fixed_now,
        broker=broker,
        price=1.3000,
        risk_per_trade=0.8,
        family_name="fx_pullback",
        stop_loss_price=1.2990,
        sizing_profile={
            "mode": BrokerSizingMode.EXACT_POINT_VALUE.value,
            "price_increment": 0.0001,
            "value_per_increment": 1.0,
        },
    )
    service = CapitalAllocatorService(session)
    service.settings.allocation_max_risk_per_family_percent = 1.5

    decision = service.allocate([candidate], received_at=fixed_now)[0]

    assert decision.selected is True
    assert decision.binding_budget == "family_risk"
    assert decision.allocated_risk_percent == pytest.approx(0.1)


def test_allocator_rounds_up_to_minimum_deal_size_without_exceeding_hard_budget(session, broker, fixed_now):
    broker.account_summary = BrokerAccountSummary(
        account_id="round-up-safe",
        balance=47.5,
        available=47.5,
        profit_loss=0.0,
        equity=47.5,
        account_type=AccountType.DEMO,
    )
    candidate = _candidate(
        strategy_name="smoke_test_hold",
        instrument="IX.D.FTSE.DAILY.IP",
        direction=OrderDirection.BUY,
        signal_at=fixed_now,
        broker=broker,
        price=100.0,
        risk_per_trade=1.0,
        min_deal_size=1.0,
    )
    service = CapitalAllocatorService(session)
    service.settings.allocation_max_risk_per_strategy_percent = 2.0
    service.settings.allocation_max_risk_per_family_percent = 2.0
    service.settings.allocation_max_risk_per_instrument_percent = 2.0
    service.settings.allocation_max_risk_per_currency_percent = 2.0
    service.settings.allocation_max_gross_exposure_percent = 500.0

    decision = service.allocate([candidate], received_at=fixed_now)[0]

    assert decision.selected is True
    assert decision.normalized_size == pytest.approx(1.0)
    assert decision.allocated_risk_percent <= 2.0
    assert "rounded_up_to_minimum_deal_size" in decision.notes


def test_allocator_rejects_round_up_when_hard_budget_would_be_exceeded(session, broker, fixed_now):
    broker.account_summary = BrokerAccountSummary(
        account_id="round-up-hard-budget",
        balance=47.5,
        available=47.5,
        profit_loss=0.0,
        equity=47.5,
        account_type=AccountType.DEMO,
    )
    candidate = _candidate(
        strategy_name="smoke_test_hold",
        instrument="IX.D.FTSE.DAILY.IP",
        direction=OrderDirection.BUY,
        signal_at=fixed_now,
        broker=broker,
        price=100.0,
        risk_per_trade=1.0,
        min_deal_size=1.0,
    )
    service = CapitalAllocatorService(session)
    service.settings.allocation_max_risk_per_strategy_percent = 1.0
    service.settings.allocation_max_risk_per_family_percent = 1.0
    service.settings.allocation_max_risk_per_instrument_percent = 1.0
    service.settings.allocation_max_risk_per_currency_percent = 1.0
    service.settings.allocation_max_gross_exposure_percent = 500.0

    decision = service.allocate([candidate], received_at=fixed_now)[0]

    assert decision.selected is False
    assert decision.reason_code == "below_min_size"


def test_trade_decision_service_persists_allocation_audit_on_rejection(session, broker, fixed_now):
    runtime_manager.last_price_updated_at["IX.D.FTSE.DAILY.IP"] = fixed_now
    broker.account_summary = BrokerAccountSummary(
        account_id="audit",
        balance=10.0,
        available=10.0,
        profit_loss=0.0,
        equity=10.0,
        account_type=AccountType.DEMO,
    )
    candidate = _candidate(
        strategy_name="smoke_test_hold",
        instrument="IX.D.FTSE.DAILY.IP",
        direction=OrderDirection.BUY,
        signal_at=fixed_now - timedelta(seconds=30),
        broker=broker,
        price=100.0,
        risk_per_trade=1.0,
    )

    result = TradeDecisionService(session).decide_signal_candidates([candidate], received_at=fixed_now)[0]
    intent = TradeService(session).list_trade_intents(limit=1)[0]

    assert result.admitted is False
    assert intent.state == "REJECTED"
    assert ((intent.details or {}).get("allocation") or {}).get("priority_score") is not None
    assert intent.decision_reason_code == "stale_signal"
