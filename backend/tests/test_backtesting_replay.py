from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.backtesting.candles import HistoricalCandle, PriceBar
from app.backtesting.clock import SimulatedClock
from app.backtesting.execution import ExecutionAssumptions
from app.backtesting.replay import BacktestReplayEngine, ReplayConfiguration
from app.core.broker import OrderDirection
from app.strategies.base import PriceUpdate, Strategy


START = datetime(2026, 1, 1, tzinfo=UTC)


class ImmediateHoldStrategy(Strategy):
    name = "immediate_hold"

    def __init__(self, *, order_log: list[str] | None = None) -> None:
        self.updates: list[float] = []
        self.order_log = order_log
        self.instrument = ""
        self.in_position = False
        self.opened_at: datetime | None = None
        self.last_at: datetime | None = None

    def on_price_update(self, data: PriceUpdate) -> None:
        self.updates.append(data.price)
        self.instrument = data.instrument
        self.last_at = data.received_at
        if self.order_log is not None:
            self.order_log.append(f"{data.received_at.isoformat()}:{data.instrument}")

    def should_enter_trade(self) -> bool:
        return not self.in_position

    def should_exit_trade(self) -> bool:
        return (
            self.in_position
            and self.opened_at is not None
            and self.last_at is not None
            and self.last_at > self.opened_at
        )

    def entry_direction(self) -> OrderDirection:
        return OrderDirection.BUY

    def on_position_opened(
        self, *, direction: OrderDirection, entry_price: float
    ) -> None:
        self.in_position = True
        self.opened_at = self.last_at

    def on_position_closed(self) -> None:
        self.in_position = False


def _candles(instrument: str) -> list[HistoricalCandle]:
    return [
        HistoricalCandle(
            timestamp=START + timedelta(minutes=index),
            instrument=instrument,
            timeframe="1m",
            trade=PriceBar(price, price + 1, price - 1, price),
        )
        for index, price in enumerate([100.0, 101.0, 102.0, 103.0])
    ]


def _run(strategies: dict[str, Strategy]):
    return BacktestReplayEngine(
        strategies=strategies,
        configuration=ReplayConfiguration(
            starting_capital=1000,
            position_sizing_mode="FIXED_UNITS",
            risk_configuration={"fixed_size": 1, "max_open_positions": 2},
            execution_assumptions=ExecutionAssumptions(
                spread_model="FIXED_PRICE", spread_value=0
            ),
            open_position_treatment="CLOSE_AT_END",
        ),
        clock=SimulatedClock(START),
    ).run({instrument: _candles(instrument) for instrument in strategies})


def test_replay_is_deterministic_and_executes_signal_at_next_open():
    first = _run({"A": ImmediateHoldStrategy()})
    second = _run({"A": ImmediateHoldStrategy()})

    assert first.metrics == second.metrics
    assert first.trades == second.trades
    assert first.trades[0].position.open_time == START + timedelta(minutes=1)


def test_strategy_cannot_receive_future_candles_during_evaluation():
    strategy = ImmediateHoldStrategy()
    result = _run({"A": strategy})

    assert strategy.updates == [100.0, 101.0, 102.0, 103.0]
    assert result.trades[0].position.metadata["signal_at"] == START.isoformat()
    assert result.trades[0].position.open_price == 101.0


def test_shortlist_replay_uses_stable_instrument_order_for_equal_timestamps():
    order: list[str] = []
    _run(
        {
            "B": ImmediateHoldStrategy(order_log=order),
            "A": ImmediateHoldStrategy(order_log=order),
        }
    )

    assert order[:2] == [
        f"{START.isoformat()}:A",
        f"{START.isoformat()}:B",
    ]
