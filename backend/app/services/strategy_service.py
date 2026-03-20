from sqlmodel import Session, select

from app.core.runtime import runtime_manager
from app.models.trade import Position
from app.services.trade_service import TradeService


class StrategyService:
    def __init__(self, session: Session | None = None):
        self.session = session

    def list_strategies(self) -> list[dict[str, str]]:
        return runtime_manager.list_strategies()

    def start_strategy(self, strategy_name: str, instrument: str) -> None:
        runtime_manager.start(strategy_name=strategy_name, instrument=instrument)

    def stop_strategy(self, instrument: str) -> None:
        runtime_manager.stop(instrument=instrument)

    def process_price_update(self, instrument: str, price: float) -> None:
        if self.session is None:
            raise ValueError("A database session is required to process price updates.")

        trade_service = TradeService(self.session)
        trade = runtime_manager.process_price_update(instrument=instrument, price=price)
        engine = runtime_manager.engines.get(instrument)

        if engine and engine.current_position is not None:
            existing_position = self.session.exec(
                select(Position).where(Position.instrument == instrument, Position.is_open.is_(True))
            ).first()
            if existing_position is None:
                trade_service.upsert_position(engine.current_position)

        if trade is not None:
            existing_position = self.session.exec(
                select(Position).where(Position.instrument == instrument, Position.is_open.is_(True))
            ).first()
            if existing_position is not None:
                existing_position.is_open = False
                existing_position.close_price = trade.close_price
                existing_position.close_time = trade.close_time
                existing_position.pnl = trade.pnl
                trade_service.close_position(existing_position)
            trade_service.record_trade(trade)
