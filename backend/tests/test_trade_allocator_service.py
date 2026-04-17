from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.core.broker import BrokerMarketDetails, OrderDirection
from app.core.signals import EntrySignal, SignalCandidate, SignalKind
from app.models.trade import Position
from app.services.trade_allocator_service import TradeAllocatorService


def _candidate(
    *,
    strategy_name: str,
    instrument: str,
    direction: OrderDirection,
    signal_at: datetime,
    confidence: float,
    risk_percent: float,
    broker,
) -> SignalCandidate:
    engine = SimpleNamespace(
        strategy=SimpleNamespace(name=strategy_name),
        broker=broker,
        instrument=instrument,
    )
    signal = EntrySignal(
        kind=SignalKind.ENTRY,
        strategy_name=strategy_name,
        instrument=instrument,
        observed_price=1.1001,
        signal_at=signal_at,
        direction=direction,
        size=1.0,
        risk_percent=risk_percent,
        bid=1.1000,
        ask=1.1002,
        market_status="TRADEABLE",
        tradable=True,
    )
    return SignalCandidate(
        strategy_name=strategy_name,
        instrument=instrument,
        signal=signal,
        engine=engine,
        source_tier="TIER1",
        confidence=confidence,
    )


def test_trade_allocator_rejects_stale_entry_candidates(session, broker, fixed_now):
    allocator = TradeAllocatorService(session)
    allocator.settings.trade_allocator_signal_stale_after_seconds = 5
    candidate = _candidate(
        strategy_name="mean_reversion",
        instrument="CS.D.EURUSD.MINI.IP",
        direction=OrderDirection.BUY,
        signal_at=fixed_now,
        confidence=0.8,
        risk_percent=0.5,
        broker=broker,
    )

    decisions = allocator.allocate([candidate], received_at=fixed_now + timedelta(seconds=20))

    assert len(decisions) == 1
    assert decisions[0].selected is False
    assert decisions[0].reason_code == "stale_signal"


def test_trade_allocator_keeps_highest_scoring_duplicate_and_conflict(session, broker, fixed_now):
    allocator = TradeAllocatorService(session)
    instrument = "CS.D.EURUSD.MINI.IP"
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

    strong_buy = _candidate(
        strategy_name="breakout_guard",
        instrument=instrument,
        direction=OrderDirection.BUY,
        signal_at=fixed_now,
        confidence=0.95,
        risk_percent=0.7,
        broker=broker,
    )
    weak_buy = _candidate(
        strategy_name="carry_drift",
        instrument=instrument,
        direction=OrderDirection.BUY,
        signal_at=fixed_now,
        confidence=0.35,
        risk_percent=0.7,
        broker=broker,
    )
    sell_conflict = _candidate(
        strategy_name="mean_reversion",
        instrument=instrument,
        direction=OrderDirection.SELL,
        signal_at=fixed_now,
        confidence=0.7,
        risk_percent=0.7,
        broker=broker,
    )

    decisions = allocator.allocate([weak_buy, strong_buy, sell_conflict], received_at=fixed_now)

    selected = [decision for decision in decisions if decision.selected]
    rejected = {decision.reason_code for decision in decisions if not decision.selected}
    assert len(selected) == 1
    assert selected[0].candidate.strategy_name == "breakout_guard"
    assert rejected == {"weaker_duplicate", "direction_conflict"}


def test_trade_allocator_respects_cycle_and_open_risk_capacity(session, broker, fixed_now):
    allocator = TradeAllocatorService(session)
    allocator.settings.trade_allocator_max_decisions_per_cycle = 1
    allocator.settings.runtime_max_open_risk_percent = 1.0
    instrument_a = "CS.D.EURUSD.MINI.IP"
    instrument_b = "IX.D.NASDAQ.DAILY.IP"
    broker.market_details_by_instrument[instrument_a] = BrokerMarketDetails(
        instrument=instrument_a,
        name=instrument_a,
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
    broker.market_details_by_instrument[instrument_b] = BrokerMarketDetails(
        instrument=instrument_b,
        name=instrument_b,
        bid=18000.0,
        offer=18000.5,
        high=18020.0,
        low=17980.0,
        percentage_change=0.0,
        net_change=0.0,
        market_status="TRADEABLE",
        update_time=fixed_now.isoformat(),
        tradable=True,
    )
    session.add(
        Position(
            strategy_name="existing_strategy",
            broker_reference="pos-1",
            instrument="IX.D.SP500.DAILY.IP",
            direction="BUY",
            size=1.0,
            open_price=5000.0,
            open_time=fixed_now,
            risk_percent=0.6,
            account_type="DEMO",
            is_open=True,
        )
    )
    session.commit()

    high_score = _candidate(
        strategy_name="breakout_guard",
        instrument=instrument_a,
        direction=OrderDirection.BUY,
        signal_at=fixed_now,
        confidence=0.95,
        risk_percent=0.3,
        broker=broker,
    )
    risk_blocked = _candidate(
        strategy_name="carry_drift",
        instrument=instrument_b,
        direction=OrderDirection.BUY,
        signal_at=fixed_now,
        confidence=0.8,
        risk_percent=0.5,
        broker=broker,
    )

    decisions = allocator.allocate([high_score, risk_blocked], received_at=fixed_now)

    selected = [decision for decision in decisions if decision.selected]
    rejected = {decision.candidate.strategy_name: decision.reason_code for decision in decisions if not decision.selected}
    assert len(selected) == 1
    assert selected[0].candidate.strategy_name == "breakout_guard"
    assert rejected["carry_drift"] in {"cycle_capacity", "open_risk_capacity"}


def test_trade_allocator_rejects_instrument_when_exposure_limit_already_used(session, broker, fixed_now):
    allocator = TradeAllocatorService(session)
    allocator.settings.trade_allocator_max_open_positions_per_instrument = 1
    instrument = "CS.D.EURUSD.MINI.IP"
    session.add(
        Position(
            strategy_name="existing_strategy",
            broker_reference="pos-2",
            instrument=instrument,
            direction="BUY",
            size=1.0,
            open_price=1.1000,
            open_time=fixed_now,
            risk_percent=0.3,
            account_type="DEMO",
            is_open=True,
        )
    )
    session.commit()
    candidate = _candidate(
        strategy_name="mean_reversion",
        instrument=instrument,
        direction=OrderDirection.BUY,
        signal_at=fixed_now,
        confidence=0.8,
        risk_percent=0.4,
        broker=broker,
    )

    decisions = allocator.allocate([candidate], received_at=fixed_now)

    assert len(decisions) == 1
    assert decisions[0].selected is False
    assert decisions[0].reason_code == "instrument_exposure_limit"
