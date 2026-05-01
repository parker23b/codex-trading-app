from __future__ import annotations

from datetime import timedelta

from app.core.broker import OrderDirection
from app.core.runtime import runtime_manager
from app.core.signals import EntrySignal, SignalKind, SignalStatus
from app.models.trade import Position, TradeIntent, TradeIntentState
from app.services.portfolio_risk_service import PortfolioRiskService
from app.services.runtime_state_service import RuntimeStateService


INSTRUMENT = "CS.D.EURUSD.MINI.IP"


def make_entry_signal(*, signal_at, observed_price: float = 100.0) -> EntrySignal:
    return EntrySignal(
        kind=SignalKind.ENTRY,
        strategy_name="smoke_test_hold",
        instrument=INSTRUMENT,
        observed_price=observed_price,
        signal_at=signal_at,
        direction=OrderDirection.BUY,
        size=1.0,
        risk_percent=0.8,
        bid=99.95,
        ask=100.05,
        market_status="TRADEABLE",
        tradable=True,
    )


def test_assess_entry_rejects_stale_market_data(session, fixed_now):
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now - timedelta(
        seconds=30
    )
    signal = make_entry_signal(signal_at=fixed_now)

    result = PortfolioRiskService(session).assess_entry(
        signal, open_positions=[], trades=[]
    )

    assert result.status is SignalStatus.REJECTED
    assert result.rejection_layer == "market_quality"
    stale_check = next(
        check
        for layer in result.audit_trail
        if layer["layer"] == "market_quality"
        for check in layer["checks"]
        if check["code"] == "stale_price_gate"
    )
    assert stale_check["passed"] is False
    assert stale_check["reason"] == "Latest price update is stale."


def test_assess_entry_rejects_duplicate_signal_within_suppression_window(
    session, fixed_now, monkeypatch
):
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    recent_intent = TradeIntent(
        strategy_name="mean_reversion",
        instrument=INSTRUMENT,
        direction=OrderDirection.BUY.value,
        state=TradeIntentState.SUBMITTED.value,
        signal_time=fixed_now - timedelta(seconds=8),
        created_at=fixed_now - timedelta(seconds=5),
    )
    monkeypatch.setattr(
        PortfolioRiskService,
        "_load_recent_entry_trade_intents",
        lambda self, signal: [recent_intent],
    )
    signal = make_entry_signal(signal_at=fixed_now)
    signal.strategy_name = "mean_reversion"

    result = PortfolioRiskService(session).assess_entry(
        signal, open_positions=[], trades=[]
    )

    assert result.status is SignalStatus.REJECTED
    assert result.rejection_layer == "pre_trade"
    duplicate_check = next(
        check
        for layer in result.audit_trail
        if layer["layer"] == "pre_trade"
        for check in layer["checks"]
        if check["code"] == "duplicate_signal_suppression"
    )
    assert duplicate_check["passed"] is False
    assert duplicate_check["actual"] == 1


def test_assess_entry_uses_trade_intent_failures_for_retry_cooldown(
    session, fixed_now, monkeypatch
):
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    failed_intent = TradeIntent(
        strategy_name="mean_reversion",
        instrument=INSTRUMENT,
        direction=OrderDirection.BUY.value,
        state=TradeIntentState.FAILED.value,
        signal_time=fixed_now - timedelta(seconds=20),
        created_at=fixed_now - timedelta(seconds=10),
    )
    monkeypatch.setattr(
        PortfolioRiskService,
        "_load_recent_entry_trade_intents",
        lambda self, signal: [failed_intent],
    )
    signal = make_entry_signal(signal_at=fixed_now)
    signal.strategy_name = "mean_reversion"

    result = PortfolioRiskService(session).assess_entry(
        signal, open_positions=[], trades=[]
    )

    assert result.status is SignalStatus.REJECTED
    assert result.rejection_layer == "pre_trade"
    failed_check = next(
        check
        for layer in result.audit_trail
        if layer["layer"] == "pre_trade"
        for check in layer["checks"]
        if check["code"] == "failed_entry_retry_cooldown"
    )
    assert failed_check["passed"] is False


def test_assess_entry_rejects_projected_open_risk_breach(session, fixed_now):
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    existing_position = Position(
        strategy_name="mean_reversion",
        broker_reference="pos-1",
        instrument="IX.D.FTSE.DAILY.IP",
        direction="BUY",
        size=1.0,
        open_price=10_000.0,
        open_time=fixed_now - timedelta(minutes=5),
        current_price=10_010.0,
        unrealized_pnl=10.0,
        risk_percent=3.5,
        account_type="DEMO",
        is_open=True,
    )
    signal = make_entry_signal(signal_at=fixed_now)
    signal.strategy_name = "mean_reversion"
    signal.risk_percent = 1.0

    result = PortfolioRiskService(session).assess_entry(
        signal, open_positions=[existing_position], trades=[]
    )

    assert result.status is SignalStatus.REJECTED
    assert result.rejection_layer == "portfolio"
    summary = result.audit_summary
    assert summary["open_risk_percent"] == 3.5
    risk_check = next(
        check
        for layer in result.audit_trail
        if layer["layer"] == "portfolio"
        for check in layer["checks"]
        if check["code"] == "portfolio_open_risk"
    )
    assert risk_check["passed"] is False
    assert risk_check["actual"] == 4.5


def test_assess_entry_rejects_when_global_kill_switch_is_active(session, fixed_now):
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    signal = make_entry_signal(signal_at=fixed_now)
    risk_service = PortfolioRiskService(session)
    risk_service.settings.runtime_global_entry_kill_switch = True

    result = risk_service.assess_entry(signal, open_positions=[], trades=[])

    assert result.status is SignalStatus.REJECTED
    assert result.rejection_layer == "kill_switch"
    kill_switch_check = next(
        check
        for layer in result.audit_trail
        if layer["layer"] == "kill_switch"
        for check in layer["checks"]
        if check["code"] == "global_entry_kill_switch"
    )
    assert kill_switch_check["passed"] is False
    assert kill_switch_check["actual"] is True


def test_assess_entry_rejects_when_runtime_is_marked_unhealthy(session, fixed_now):
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now
    runtime_manager.start(strategy_name="smoke_test_hold", instrument=INSTRUMENT)
    runtime_service = RuntimeStateService(session)
    runtime_service.sync_engine_state(
        strategy_name="smoke_test_hold",
        instrument=INSTRUMENT,
        status="RUNNING",
        recovery_state="RUNNING",
        current_position=None,
    )
    runtime_service.mark_recovery_state(
        strategy_name="smoke_test_hold",
        instrument=INSTRUMENT,
        recovery_state="ERROR",
        recovery_reason="stream stalled",
    )
    signal = make_entry_signal(signal_at=fixed_now)

    result = PortfolioRiskService(session).assess_entry(
        signal, open_positions=[], trades=[]
    )

    assert result.status is SignalStatus.REJECTED
    assert result.rejection_layer == "platform_health"
    health_check = next(
        check
        for layer in result.audit_trail
        if layer["layer"] == "platform_health"
        for check in layer["checks"]
        if check["code"] == "runtime_recovery_state"
    )
    assert health_check["passed"] is False
    assert health_check["actual"] == 1
