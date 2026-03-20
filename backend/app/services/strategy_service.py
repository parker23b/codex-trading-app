from collections import defaultdict

from sqlmodel import Session

from app.core.config import get_settings
from app.core.instrument_catalog import list_instruments
from app.core.runtime import runtime_manager
from app.strategies.registry import strategy_registry
from app.services.trade_service import TradeService


class StrategyService:
    def __init__(self, session: Session | None = None):
        self.session = session
        self.settings = get_settings()

    def list_strategies(self) -> list[dict[str, object]]:
        if self.session is None:
            raise ValueError("A database session is required to list strategies.")

        trade_service = TradeService(self.session)
        trades = trade_service.list_trades()
        positions = trade_service.list_positions()
        open_positions_by_strategy = {position.strategy_name: position for position in positions}
        trades_by_strategy: dict[str, list[float]] = defaultdict(list)
        for trade in trades:
            trades_by_strategy[trade.strategy_name].append(trade.pnl)

        strategies: list[dict[str, object]] = []
        for metadata in runtime_manager.list_registered_strategies():
            engine = runtime_manager.get_engine_for_strategy(metadata.name)
            position = open_positions_by_strategy.get(metadata.name)
            strategy_pnls = trades_by_strategy.get(metadata.name, [])
            trade_count = len(strategy_pnls)
            win_count = len([pnl for pnl in strategy_pnls if pnl > 0])
            current_pnl = position.unrealized_pnl if position and position.unrealized_pnl is not None else 0.0
            strategies.append(
                {
                    "name": metadata.name,
                    "description": metadata.description,
                    "instrument": engine.instrument if engine else metadata.default_instrument,
                    "status": "RUNNING" if engine else "STOPPED",
                    "current_pnl": round(current_pnl, 2),
                    "last_price": runtime_manager.get_last_price(engine.instrument) if engine else None,
                    "trade_count": trade_count,
                    "win_rate": round((win_count / trade_count) * 100, 2) if trade_count else 0.0,
                    "account_type": self.settings.broker_mode,
                    "position_size": metadata.position_size,
                    "risk_per_trade": metadata.risk_per_trade,
                    "instrument_options": list_instruments(),
                    "parameters": [
                        {
                            "key": parameter.key,
                            "label": parameter.label,
                            "value": parameter.value,
                            "step": parameter.step,
                        }
                        for parameter in metadata.parameters
                    ],
                }
            )
        return strategies

    def start_strategy(self, strategy_name: str, instrument: str) -> None:
        runtime_manager.start(strategy_name=strategy_name, instrument=instrument)

    def stop_strategy(self, instrument: str | None = None, strategy_name: str | None = None) -> None:
        if instrument is None:
            if strategy_name is None:
                raise ValueError("Either instrument or strategy_name must be provided.")
            engine = runtime_manager.get_engine_for_strategy(strategy_name)
            if engine is None:
                raise ValueError(f"No active strategy named '{strategy_name}'.")
            instrument = engine.instrument
        runtime_manager.stop(instrument=instrument)

    def process_price_update(self, instrument: str, price: float) -> None:
        if self.session is None:
            raise ValueError("A database session is required to process price updates.")

        trade_service = TradeService(self.session)
        trade = runtime_manager.process_price_update(instrument=instrument, price=price)
        engine = runtime_manager.engines.get(instrument)
        metadata = strategy_registry.get_metadata(engine.strategy.name) if engine else None

        if engine and engine.current_position is not None:
            existing_position = trade_service.get_open_position(instrument)
            risk_percent = metadata.risk_per_trade if metadata else 0.0
            unrealized_pnl = self._calculate_open_pnl(
                direction=engine.current_position.direction,
                open_price=engine.current_position.open_price,
                current_price=price,
                size=engine.current_position.size,
            )
            if existing_position is None:
                engine.current_position.current_price = price
                engine.current_position.unrealized_pnl = round(unrealized_pnl, 2)
                engine.current_position.risk_percent = risk_percent
                engine.current_position.reason = f"{engine.strategy.name} signal active"
                trade_service.upsert_position(engine.current_position)
            else:
                existing_position.current_price = price
                existing_position.unrealized_pnl = round(unrealized_pnl, 2)
                existing_position.risk_percent = risk_percent
                existing_position.pnl = round(unrealized_pnl, 2)
                trade_service.upsert_position(existing_position)
        elif engine is not None:
            existing_position = trade_service.get_open_position(instrument)
            if existing_position is not None:
                existing_position.current_price = price
                existing_position.unrealized_pnl = self._calculate_open_pnl(
                    direction=existing_position.direction,
                    open_price=existing_position.open_price,
                    current_price=price,
                    size=existing_position.size,
                )
                trade_service.upsert_position(existing_position)

        if trade is not None:
            trade.outcome = "win" if trade.pnl > 0 else "loss"
            risk_budget = metadata.risk_per_trade if metadata and metadata.risk_per_trade else 1.0
            trade.r_multiple = round(trade.pnl / risk_budget, 2)
            trade.reason = f"{trade.strategy_name} exit triggered"
            existing_position = trade_service.get_open_position(instrument)
            if existing_position is not None:
                existing_position.is_open = False
                existing_position.close_price = trade.close_price
                existing_position.close_time = trade.close_time
                existing_position.pnl = trade.pnl
                existing_position.current_price = trade.close_price
                existing_position.unrealized_pnl = 0.0
                trade_service.close_position(existing_position)
            trade_service.record_trade(trade)

    @staticmethod
    def _calculate_open_pnl(*, direction: str, open_price: float, current_price: float, size: float) -> float:
        multiplier = 1 if direction == "BUY" else -1
        return (current_price - open_price) * size * multiplier
