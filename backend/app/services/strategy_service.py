from collections import defaultdict
from datetime import UTC, datetime

from sqlmodel import Session

from app.core.config import get_settings
from app.core.ig_broker import IGBrokerError
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
            price_snapshot = (
                self._resolve_price_snapshot(engine.instrument, position.current_price if position else None) if engine else None
            )
            strategies.append(
                {
                    "name": metadata.name,
                    "description": metadata.description,
                    "instrument": engine.instrument if engine else metadata.default_instrument,
                    "status": "RUNNING" if engine else "STOPPED",
                    "current_pnl": round(current_pnl, 2),
                    "last_price": price_snapshot["price"] if price_snapshot else None,
                    "price_status": price_snapshot["status"] if price_snapshot else "STOPPED",
                    "price_error": price_snapshot["error"] if price_snapshot else None,
                    "last_price_updated_at": price_snapshot["updated_at"] if price_snapshot else None,
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

    def process_price_update(
        self,
        instrument: str,
        price: float,
        *,
        bid: float | None = None,
        ask: float | None = None,
        high: float | None = None,
        low: float | None = None,
        market_status: str | None = None,
        tradable: bool | None = None,
        received_at: datetime | None = None,
    ) -> None:
        if self.session is None:
            raise ValueError("A database session is required to process price updates.")

        trade_service = TradeService(self.session)
        trade = runtime_manager.process_price_update(
            instrument=instrument,
            price=price,
            bid=bid,
            ask=ask,
            high=high,
            low=low,
            market_status=market_status,
            tradable=tradable,
            received_at=received_at,
        )
        engine = runtime_manager.engines.get(instrument)
        metadata = strategy_registry.get_metadata(engine.strategy.name) if engine else None

        if engine and engine.current_position is not None:
            existing_position = trade_service.get_open_position(instrument)
            risk_percent = metadata.risk_per_trade if metadata else 0.0
            mark_price = self._mark_price(direction=engine.current_position.direction, price=price, bid=bid, ask=ask)
            unrealized_pnl = self._calculate_open_pnl(
                direction=engine.current_position.direction,
                open_price=engine.current_position.open_price,
                current_price=mark_price,
                size=engine.current_position.size,
            )
            if existing_position is None:
                engine.current_position.current_price = mark_price
                engine.current_position.unrealized_pnl = round(unrealized_pnl, 2)
                engine.current_position.risk_percent = risk_percent
                engine.current_position.reason = f"{engine.strategy.name} signal active"
                trade_service.upsert_position(engine.current_position)
            else:
                existing_position.current_price = mark_price
                existing_position.unrealized_pnl = round(unrealized_pnl, 2)
                existing_position.risk_percent = risk_percent
                existing_position.pnl = round(unrealized_pnl, 2)
                trade_service.upsert_position(existing_position)
        elif engine is not None:
            existing_position = trade_service.get_open_position(instrument)
            if existing_position is not None:
                existing_position.current_price = self._mark_price(
                    direction=existing_position.direction,
                    price=price,
                    bid=bid,
                    ask=ask,
                )
                existing_position.unrealized_pnl = self._calculate_open_pnl(
                    direction=existing_position.direction,
                    open_price=existing_position.open_price,
                    current_price=existing_position.current_price,
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

    @staticmethod
    def _mark_price(*, direction: str, price: float, bid: float | None, ask: float | None) -> float:
        if direction == "BUY" and bid is not None:
            return bid
        if direction == "SELL" and ask is not None:
            return ask
        return price

    @staticmethod
    def _resolve_price_snapshot(instrument: str, fallback_price: float | None = None) -> dict[str, object]:
        from app.services.ig_streaming_service import get_ig_streaming_service

        streamed_price = get_ig_streaming_service().get_last_price(instrument)
        if streamed_price is not None:
            return {
                "price": streamed_price,
                "status": "LIVE",
                "error": None,
                "updated_at": get_ig_streaming_service().get_health().last_tick_at,
            }

        last_price = runtime_manager.get_last_price(instrument)
        if last_price is not None:
            updated_at = runtime_manager.get_last_price_updated_at(instrument)
            error = runtime_manager.get_price_error(instrument)
            if updated_at is None:
                status = "STALE" if error else "CACHED"
            else:
                age_seconds = (datetime.now(UTC) - updated_at.astimezone(UTC)).total_seconds()
                status = "STALE" if error or age_seconds > 10 else "POLLED"
            return {
                "price": last_price,
                "status": status,
                "error": error,
                "updated_at": updated_at,
            }

        if fallback_price is not None:
            return {
                "price": fallback_price,
                "status": "POSITION",
                "error": runtime_manager.get_price_error(instrument),
                "updated_at": runtime_manager.get_last_price_updated_at(instrument),
            }

        engine = runtime_manager.engines.get(instrument)
        if engine is None:
            return {"price": None, "status": "STOPPED", "error": None, "updated_at": None}
        try:
            price = engine.broker.get_latest_price(instrument)
            return {"price": price, "status": "REST", "error": None, "updated_at": None}
        except IGBrokerError as exc:
            return {"price": None, "status": "ERROR", "error": str(exc), "updated_at": None}
