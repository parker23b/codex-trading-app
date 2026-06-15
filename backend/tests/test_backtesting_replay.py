from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

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


class HoldWithStopStrategy(ImmediateHoldStrategy):
    def should_exit_trade(self) -> bool:
        return False

    def entry_signal_hints(self) -> dict[str, float]:
        return {"stop_loss_price": 90.0}


class ShortHoldWithStopStrategy(HoldWithStopStrategy):
    def entry_direction(self) -> OrderDirection:
        return OrderDirection.SELL

    def entry_signal_hints(self) -> dict[str, float]:
        return {"stop_loss_price": 110.0}


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
    assert (
        result.trades[0].position.metadata["signal_at"]
        == (START + timedelta(minutes=1)).isoformat()
    )
    assert result.trades[0].position.open_price == 101.0
    assert strategy.last_at == START + timedelta(minutes=4)


def test_shortlist_replay_uses_stable_instrument_order_for_equal_timestamps():
    order: list[str] = []
    _run(
        {
            "B": ImmediateHoldStrategy(order_log=order),
            "A": ImmediateHoldStrategy(order_log=order),
        }
    )

    assert order[:2] == [
        f"{(START + timedelta(minutes=1)).isoformat()}:A",
        f"{(START + timedelta(minutes=1)).isoformat()}:B",
    ]


def test_trades_use_stable_secondary_order_for_equal_open_times():
    result = _run(
        {
            "B": ImmediateHoldStrategy(),
            "A": ImmediateHoldStrategy(),
        }
    )

    ordered = [
        (trade.position.open_time, trade.position.instrument) for trade in result.trades
    ]

    assert ordered == sorted(ordered)
    assert ordered[:2] == [
        (START + timedelta(minutes=1), "A"),
        (START + timedelta(minutes=1), "B"),
    ]


def test_percent_risk_sizing_at_open_cannot_see_current_candle_close():
    rows = {
        "A": [
            HistoricalCandle(
                timestamp=START,
                instrument="A",
                timeframe="1m",
                trade=PriceBar(100, 101, 99, 100),
            ),
            HistoricalCandle(
                timestamp=START + timedelta(minutes=1),
                instrument="A",
                timeframe="1m",
                trade=PriceBar(100, 200, 99, 200),
            ),
        ],
        "B": [
            HistoricalCandle(
                timestamp=START + timedelta(minutes=index),
                instrument="B",
                timeframe="1m",
                trade=PriceBar(100, 101, 99, 100),
            )
            for index in range(2)
        ],
    }
    result = BacktestReplayEngine(
        strategies={
            "A": HoldWithStopStrategy(),
            "B": HoldWithStopStrategy(),
        },
        configuration=ReplayConfiguration(
            starting_capital=1000,
            position_sizing_mode="PERCENT_RISK",
            risk_configuration={
                "risk_per_trade_percent": 10,
                "fallback_stop_percent": 1,
                "max_open_positions": 2,
            },
            execution_assumptions=ExecutionAssumptions(
                spread_model="FIXED_PRICE", spread_value=0
            ),
            open_position_treatment="MARK_TO_MARKET",
        ),
        clock=SimulatedClock(START),
    ).run(rows)

    assert [position.position.size for position in result.open_positions] == [10, 10]


@pytest.mark.parametrize(
    ("strategy", "direction"),
    [
        (HoldWithStopStrategy(), OrderDirection.BUY),
        (ShortHoldWithStopStrategy(), OrderDirection.SELL),
    ],
)
def test_percent_risk_sizing_uses_executable_fill_slippage_and_fees(
    strategy: Strategy, direction: OrderDirection
):
    candles = [
        HistoricalCandle(
            timestamp=START + timedelta(minutes=index),
            instrument="A",
            timeframe="1m",
            trade=PriceBar(100, 101, 99, 100),
        )
        for index in range(2)
    ]
    result = BacktestReplayEngine(
        strategies={"A": strategy},
        configuration=ReplayConfiguration(
            starting_capital=1000,
            position_sizing_mode="PERCENT_RISK",
            risk_configuration={
                "risk_per_trade_percent": 10,
                "fallback_stop_percent": 1,
                "max_open_positions": 1,
            },
            execution_assumptions=ExecutionAssumptions(
                spread_model="FIXED_PRICE",
                spread_value=2,
                slippage_model="FIXED_PRICE",
                slippage_value=0.5,
                fee_model="PER_UNIT",
                fee_value=0.2,
            ),
            open_position_treatment="MARK_TO_MARKET",
        ),
        clock=SimulatedClock(START),
    ).run({"A": candles})

    open_result = result.open_positions[0]
    position = open_result.position
    assert position.direction is direction
    assert position.metadata["sizing_expected_entry_price"] == (
        101.5 if direction is OrderDirection.BUY else 98.5
    )
    assert position.metadata["sizing_projected_stop_loss"] == pytest.approx(100)
    assert position.metadata["sizing_risk_budget"] == 100
    assert position.size == pytest.approx(100 / 12.4)
    assert (
        position.metadata["sizing_projected_stop_loss"]
        <= position.metadata["sizing_risk_budget"] + 1e-9
    )


def test_end_treatment_uses_final_close_and_open_fees_reduce_equity():
    candles = [
        HistoricalCandle(
            timestamp=START,
            instrument="A",
            timeframe="1m",
            trade=PriceBar(100, 100, 100, 100),
        ),
        HistoricalCandle(
            timestamp=START + timedelta(minutes=1),
            instrument="A",
            timeframe="1m",
            trade=PriceBar(101, 110, 101, 110),
        ),
    ]

    def execute(treatment: str):
        return BacktestReplayEngine(
            strategies={"A": HoldWithStopStrategy()},
            configuration=ReplayConfiguration(
                starting_capital=1000,
                position_sizing_mode="FIXED_UNITS",
                risk_configuration={"fixed_size": 1, "max_open_positions": 1},
                execution_assumptions=ExecutionAssumptions(
                    spread_model="FIXED_PRICE",
                    spread_value=0,
                    fee_model="FIXED_PER_ORDER",
                    fee_value=2,
                ),
                open_position_treatment=treatment,
            ),
            clock=SimulatedClock(START),
        ).run({"A": candles})

    marked = execute("MARK_TO_MARKET")
    closed = execute("CLOSE_AT_END")

    assert marked.metrics["ending_cash"] == 998
    assert marked.metrics["ending_equity"] == 1007
    assert marked.metrics["realised_pnl"] == 0
    assert marked.metrics["unrealised_pnl"] == 9
    assert marked.metrics["fees_paid"] == 2
    assert marked.metrics["total_pnl"] == 7
    assert marked.metrics["open_positions_at_end"] == 1
    assert marked.metrics["headline_return_includes_unrealised"] is True
    assert closed.trades[0].close_price == 110
    assert closed.trades[0].close_time == START + timedelta(minutes=2)
    assert closed.metrics["ending_cash"] == 1005
    assert closed.metrics["ending_equity"] == 1005
    assert closed.metrics["realised_pnl"] == 9
    assert closed.metrics["unrealised_pnl"] == 0
    assert closed.metrics["fees_paid"] == 4
    assert closed.metrics["total_pnl"] == 5
    assert closed.metrics["headline_return_includes_unrealised"] is False
