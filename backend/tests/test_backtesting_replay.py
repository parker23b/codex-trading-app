from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.backtesting.candles import HistoricalCandle, PriceBar
from app.backtesting.clock import SimulatedClock
from app.backtesting.execution import ExecutionAssumptions
from app.backtesting.metrics import PERCENT_RISK_SIZING_ABSOLUTE_TOLERANCE
from app.backtesting.replay import BacktestReplayEngine, ReplayConfiguration
from app.core.broker import OrderDirection
from app.strategies.base import PriceUpdate, Strategy


START = datetime(2026, 1, 1, tzinfo=UTC)


class ImmediateHoldStrategy(Strategy):
    name = "immediate_hold"

    def __init__(
        self,
        *,
        direction: OrderDirection = OrderDirection.BUY,
        order_log: list[str] | None = None,
    ) -> None:
        self.updates: list[float] = []
        self.direction = direction
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
        return self.direction

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


class HoldWithoutStopStrategy(ImmediateHoldStrategy):
    def should_exit_trade(self) -> bool:
        return False


class SingleRoundTripStrategy(ImmediateHoldStrategy):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.has_entered = False

    def should_enter_trade(self) -> bool:
        return not self.in_position and not self.has_entered

    def on_position_opened(
        self, *, direction: OrderDirection, entry_price: float
    ) -> None:
        super().on_position_opened(direction=direction, entry_price=entry_price)
        self.has_entered = True


class ReadyAfterUpdatesStrategy(SingleRoundTripStrategy):
    def __init__(self, *, required_updates: int, **kwargs) -> None:
        super().__init__(**kwargs)
        self.required_updates = required_updates

    def should_enter_trade(self) -> bool:
        return (
            len(self.updates) >= self.required_updates and super().should_enter_trade()
        )


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


def _trade_candles(
    instrument: str,
    prices: list[float],
    *,
    historical_bid_ask: bool = False,
) -> list[HistoricalCandle]:
    rows = []
    for index, price in enumerate(prices):
        timestamp = START + timedelta(minutes=index)
        if historical_bid_ask:
            rows.append(
                HistoricalCandle(
                    timestamp=timestamp,
                    instrument=instrument,
                    timeframe="1m",
                    bid=PriceBar(price - 1, price, price - 2, price - 1),
                    ask=PriceBar(price + 1, price + 2, price, price + 1),
                )
            )
        else:
            rows.append(
                HistoricalCandle(
                    timestamp=timestamp,
                    instrument=instrument,
                    timeframe="1m",
                    trade=PriceBar(price, price + 1, price - 1, price),
                )
            )
    return rows


def _warmup_run(
    *,
    strategy: Strategy,
    prices: list[float],
    trading_start_at: datetime,
    open_position_treatment: str = "CLOSE_AT_END",
    order_log: list[str] | None = None,
):
    if order_log is not None and isinstance(strategy, ImmediateHoldStrategy):
        strategy.order_log = order_log
    return BacktestReplayEngine(
        strategies={"A": strategy},
        configuration=ReplayConfiguration(
            starting_capital=1000,
            position_sizing_mode="FIXED_UNITS",
            risk_configuration={"fixed_size": 1, "max_open_positions": 1},
            execution_assumptions=ExecutionAssumptions(spread_model="NONE"),
            open_position_treatment=open_position_treatment,
            trading_start_at=trading_start_at,
            warmup_mode="CANDLE_COUNT",
            warmup_candle_count=2,
        ),
        clock=SimulatedClock(START),
    ).run({"A": _trade_candles("A", prices)})


def test_warmup_updates_strategy_state_but_cannot_create_trades():
    trading_start = START + timedelta(minutes=2)
    strategy = ReadyAfterUpdatesStrategy(required_updates=2)

    result = _warmup_run(
        strategy=strategy,
        prices=[90, 95, 100, 101, 102],
        trading_start_at=trading_start,
    )

    assert strategy.updates[:2] == [90, 95]
    assert result.trades
    assert all(trade.position.open_time >= trading_start for trade in result.trades)
    assert result.trades[0].position.open_time == trading_start + timedelta(minutes=1)
    assert result.equity[0].timestamp == trading_start + timedelta(minutes=1)


def test_warmup_is_excluded_from_exposure_and_drawdown_curve():
    trading_start = START + timedelta(minutes=2)
    result = _warmup_run(
        strategy=HoldWithoutStopStrategy(),
        prices=[10_000, 1, 100, 100, 90],
        trading_start_at=trading_start,
    )

    assert len(result.equity) == 3
    assert all(sample.timestamp > trading_start for sample in result.equity)
    assert result.metrics["wall_clock_exposure_pct"] == pytest.approx(200 / 3)
    assert result.metrics["maximum_drawdown"] == 10


def test_zero_warmup_matches_existing_replay_behavior():
    candles = {"A": _trade_candles("A", [100, 101, 102, 103])}
    baseline = BacktestReplayEngine(
        strategies={"A": ImmediateHoldStrategy()},
        configuration=ReplayConfiguration(
            starting_capital=1000,
            position_sizing_mode="FIXED_UNITS",
            risk_configuration={"fixed_size": 1, "max_open_positions": 1},
            execution_assumptions=ExecutionAssumptions(spread_model="NONE"),
            open_position_treatment="CLOSE_AT_END",
        ),
        clock=SimulatedClock(START),
    ).run(candles)
    explicit_none = BacktestReplayEngine(
        strategies={"A": ImmediateHoldStrategy()},
        configuration=ReplayConfiguration(
            starting_capital=1000,
            position_sizing_mode="FIXED_UNITS",
            risk_configuration={"fixed_size": 1, "max_open_positions": 1},
            execution_assumptions=ExecutionAssumptions(spread_model="NONE"),
            open_position_treatment="CLOSE_AT_END",
            trading_start_at=START,
            warmup_mode="NONE",
            warmup_candle_count=0,
        ),
        clock=SimulatedClock(START),
    ).run(candles)

    assert explicit_none.trades == baseline.trades
    assert explicit_none.equity == baseline.equity
    assert explicit_none.metrics == baseline.metrics


def test_same_timestamp_ordering_is_preserved_during_warmup():
    order_log: list[str] = []
    result = BacktestReplayEngine(
        strategies={
            "B": ImmediateHoldStrategy(order_log=order_log),
            "A": ImmediateHoldStrategy(order_log=order_log),
        },
        configuration=ReplayConfiguration(
            starting_capital=1000,
            position_sizing_mode="FIXED_UNITS",
            risk_configuration={"fixed_size": 1, "max_open_positions": 2},
            execution_assumptions=ExecutionAssumptions(spread_model="NONE"),
            open_position_treatment="CLOSE_AT_END",
            trading_start_at=START + timedelta(minutes=2),
            warmup_mode="CANDLE_COUNT",
            warmup_candle_count=2,
        ),
        clock=SimulatedClock(START),
    ).run(
        {
            instrument: _trade_candles(instrument, [100, 101, 102, 103])
            for instrument in ("A", "B")
        }
    )

    assert order_log[:4] == [
        f"{(START + timedelta(minutes=1)).isoformat()}:A",
        f"{(START + timedelta(minutes=1)).isoformat()}:B",
        f"{(START + timedelta(minutes=2)).isoformat()}:A",
        f"{(START + timedelta(minutes=2)).isoformat()}:B",
    ]
    assert all(
        trade.position.open_time >= START + timedelta(minutes=2)
        for trade in result.trades
    )


def _execute_actual_fill_case(
    *,
    direction: OrderDirection,
    terminal_price: float,
    assumptions: ExecutionAssumptions,
    historical_bid_ask: bool = False,
):
    return BacktestReplayEngine(
        strategies={"A": ImmediateHoldStrategy(direction=direction)},
        configuration=ReplayConfiguration(
            starting_capital=1000,
            position_sizing_mode="FIXED_UNITS",
            risk_configuration={"fixed_size": 2, "max_open_positions": 1},
            execution_assumptions=assumptions,
            open_position_treatment="CLOSE_AT_END",
        ),
        clock=SimulatedClock(START),
    ).run(
        {
            "A": _trade_candles(
                "A",
                [100, 100, terminal_price],
                historical_bid_ask=historical_bid_ask,
            )
        }
    )


@pytest.mark.parametrize(
    (
        "direction",
        "terminal_price",
        "assumptions",
        "historical_bid_ask",
        "expected_open",
        "expected_close",
        "expected_fees",
        "expected_spread_cost",
        "expected_slippage_cost",
    ),
    [
        (
            OrderDirection.BUY,
            110,
            ExecutionAssumptions(spread_model="NONE"),
            False,
            100,
            110,
            0,
            0,
            0,
        ),
        (
            OrderDirection.BUY,
            90,
            ExecutionAssumptions(spread_model="NONE"),
            False,
            100,
            90,
            0,
            0,
            0,
        ),
        (
            OrderDirection.SELL,
            90,
            ExecutionAssumptions(spread_model="NONE"),
            False,
            100,
            90,
            0,
            0,
            0,
        ),
        (
            OrderDirection.SELL,
            110,
            ExecutionAssumptions(spread_model="NONE"),
            False,
            100,
            110,
            0,
            0,
            0,
        ),
        (
            OrderDirection.BUY,
            110,
            ExecutionAssumptions(spread_model="FIXED_PRICE", spread_value=2),
            False,
            101,
            109,
            0,
            4,
            0,
        ),
        (
            OrderDirection.BUY,
            110,
            ExecutionAssumptions(
                spread_model="NONE",
                slippage_model="FIXED_PRICE",
                slippage_value=0.5,
            ),
            False,
            100.5,
            109.5,
            0,
            0,
            2,
        ),
        (
            OrderDirection.BUY,
            110,
            ExecutionAssumptions(
                spread_model="NONE",
                fee_model="PER_UNIT",
                fee_value=0.25,
            ),
            False,
            100,
            110,
            1,
            0,
            0,
        ),
        (
            OrderDirection.BUY,
            110,
            ExecutionAssumptions(
                spread_model="NONE",
                fee_model="FIXED_PER_ORDER",
                fee_value=3,
            ),
            False,
            100,
            110,
            6,
            0,
            0,
        ),
        (
            OrderDirection.BUY,
            110,
            ExecutionAssumptions(
                spread_model="NONE",
                fee_model="BPS_NOTIONAL",
                fee_value=100,
            ),
            False,
            100,
            110,
            4.2,
            0,
            0,
        ),
        (
            OrderDirection.BUY,
            110,
            ExecutionAssumptions(spread_model="DATASET"),
            True,
            101,
            109,
            0,
            4,
            0,
        ),
    ],
)
def test_integrated_actual_fill_accounting_identity(
    direction,
    terminal_price,
    assumptions,
    historical_bid_ask,
    expected_open,
    expected_close,
    expected_fees,
    expected_spread_cost,
    expected_slippage_cost,
):
    result = _execute_actual_fill_case(
        direction=direction,
        terminal_price=terminal_price,
        assumptions=assumptions,
        historical_bid_ask=historical_bid_ask,
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    expected_gross = (
        (expected_close - expected_open) * 2
        if direction is OrderDirection.BUY
        else (expected_open - expected_close) * 2
    )
    expected_total = expected_gross - expected_fees
    assert trade.position.open_price == pytest.approx(expected_open)
    assert trade.close_price == pytest.approx(expected_close)
    assert trade.gross_pnl == pytest.approx(expected_gross)
    assert trade.fees == pytest.approx(expected_fees)
    assert trade.spread_cost == pytest.approx(expected_spread_cost)
    assert trade.slippage_cost == pytest.approx(expected_slippage_cost)
    assert trade.net_pnl == pytest.approx(expected_total)
    assert result.metrics["realised_pnl"] == pytest.approx(expected_gross)
    assert result.metrics["unrealised_pnl"] == 0
    assert result.metrics["fees_paid"] == pytest.approx(expected_fees)
    assert result.metrics["total_pnl"] == pytest.approx(expected_total)
    assert result.metrics["ending_cash"] == pytest.approx(1000 + expected_total)
    assert result.metrics["ending_equity"] == pytest.approx(1000 + expected_total)
    assert result.metrics["spread_cost"] == pytest.approx(expected_spread_cost)
    assert result.metrics["slippage_cost"] == pytest.approx(expected_slippage_cost)
    assert result.metrics["wall_clock_exposure_pct"] == pytest.approx(100 / 3)
    assert result.metrics["ending_equity"] == pytest.approx(
        result.metrics["starting_capital"]
        + result.metrics["realised_pnl"]
        + result.metrics["unrealised_pnl"]
        - result.metrics["fees_paid"]
    )


def test_integrated_mixed_closed_and_open_accounting_and_union_exposure():
    result = BacktestReplayEngine(
        strategies={
            "CLOSED": SingleRoundTripStrategy(),
            "OPEN": HoldWithoutStopStrategy(),
        },
        configuration=ReplayConfiguration(
            starting_capital=1000,
            position_sizing_mode="FIXED_UNITS",
            risk_configuration={"fixed_size": 1, "max_open_positions": 2},
            execution_assumptions=ExecutionAssumptions(spread_model="NONE"),
            open_position_treatment="MARK_TO_MARKET",
        ),
        clock=SimulatedClock(START),
    ).run(
        {
            instrument: _trade_candles(instrument, [100, 100, 105, 110])
            for instrument in ("CLOSED", "OPEN")
        }
    )

    closed = result.trades[0]
    open_result = result.open_positions[0]
    expected_realised = closed.gross_pnl
    expected_unrealised = (
        open_result.mark_price - open_result.position.open_price
    ) * open_result.position.size
    expected_fees = closed.fees + open_result.position.entry_fee
    assert result.metrics["realised_pnl"] == pytest.approx(expected_realised)
    assert result.metrics["unrealised_pnl"] == pytest.approx(expected_unrealised)
    assert result.metrics["fees_paid"] == pytest.approx(expected_fees)
    assert result.metrics["total_pnl"] == pytest.approx(
        expected_realised + expected_unrealised - expected_fees
    )
    assert result.metrics["ending_cash"] == pytest.approx(
        1000 + closed.net_pnl - open_result.position.entry_fee
    )
    assert result.metrics["ending_equity"] == pytest.approx(
        result.metrics["ending_cash"] + expected_unrealised
    )
    assert result.metrics["open_positions_at_end"] == 1
    assert result.metrics["wall_clock_exposure_pct"] == pytest.approx(75)


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


@pytest.mark.parametrize(
    (
        "direction",
        "assumptions",
        "use_fallback_stop",
        "max_size",
    ),
    [
        (
            OrderDirection.BUY,
            ExecutionAssumptions(
                spread_model="FIXED_PRICE",
                spread_value=2,
                slippage_model="FIXED_PRICE",
                slippage_value=0.5,
                fee_model="PER_UNIT",
                fee_value=0.2,
            ),
            False,
            None,
        ),
        (
            OrderDirection.SELL,
            ExecutionAssumptions(
                spread_model="FIXED_PRICE",
                spread_value=2,
                slippage_model="FIXED_PRICE",
                slippage_value=0.5,
                fee_model="PER_UNIT",
                fee_value=0.2,
            ),
            False,
            None,
        ),
        (
            OrderDirection.BUY,
            ExecutionAssumptions(
                spread_model="NONE",
                fee_model="FIXED_PER_ORDER",
                fee_value=2,
            ),
            False,
            None,
        ),
        (
            OrderDirection.BUY,
            ExecutionAssumptions(
                spread_model="NONE",
                fee_model="BPS_NOTIONAL",
                fee_value=100,
            ),
            False,
            None,
        ),
        (
            OrderDirection.BUY,
            ExecutionAssumptions(
                spread_model="NONE",
                fee_model="PER_UNIT",
                fee_value=0.2,
            ),
            True,
            None,
        ),
        (
            OrderDirection.BUY,
            ExecutionAssumptions(
                spread_model="FIXED_PRICE",
                spread_value=2,
                slippage_model="FIXED_PRICE",
                slippage_value=0.5,
                fee_model="PER_UNIT",
                fee_value=0.2,
            ),
            False,
            5,
        ),
    ],
)
def test_percent_risk_actual_stop_loss_respects_persisted_tolerance(
    direction,
    assumptions,
    use_fallback_stop,
    max_size,
):
    strategy: Strategy
    if use_fallback_stop:
        strategy = HoldWithoutStopStrategy(direction=direction)
    elif direction is OrderDirection.BUY:
        strategy = HoldWithStopStrategy()
    else:
        strategy = ShortHoldWithStopStrategy()
    stop_candle = (
        PriceBar(100, 101, 89, 90)
        if direction is OrderDirection.BUY
        else PriceBar(100, 111, 99, 110)
    )
    candles = [
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
            trade=PriceBar(100, 101, 99, 100),
        ),
        HistoricalCandle(
            timestamp=START + timedelta(minutes=2),
            instrument="A",
            timeframe="1m",
            trade=stop_candle,
        ),
    ]
    risk_configuration = {
        "risk_per_trade_percent": 10,
        "fallback_stop_percent": 10,
        "max_open_positions": 1,
    }
    if max_size is not None:
        risk_configuration["max_size"] = max_size
    result = BacktestReplayEngine(
        strategies={"A": strategy},
        configuration=ReplayConfiguration(
            starting_capital=1000,
            position_sizing_mode="PERCENT_RISK",
            risk_configuration=risk_configuration,
            execution_assumptions=assumptions,
            open_position_treatment="CLOSE_AT_END",
        ),
        clock=SimulatedClock(START),
    ).run({"A": candles})

    assert len(result.trades) == 1
    trade = result.trades[0]
    metadata = trade.position.metadata
    actual_loss = -trade.net_pnl
    assert trade.exit_reason == "STOP_LOSS"
    assert trade.position.stop_loss_price == pytest.approx(
        metadata["sizing_stop_price"]
    )
    assert metadata["sizing_absolute_tolerance"] == (
        PERCENT_RISK_SIZING_ABSOLUTE_TOLERANCE
    )
    assert result.metrics["percent_risk_sizing_absolute_tolerance"] == (
        PERCENT_RISK_SIZING_ABSOLUTE_TOLERANCE
    )
    assert actual_loss == pytest.approx(metadata["sizing_projected_stop_loss"])
    assert actual_loss <= (
        metadata["sizing_risk_budget"] + metadata["sizing_absolute_tolerance"]
    )
    if max_size is not None:
        assert trade.position.size == max_size
        assert actual_loss < metadata["sizing_risk_budget"]


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
