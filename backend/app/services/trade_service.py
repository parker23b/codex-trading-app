from datetime import datetime

from sqlmodel import Session, desc, select

from app.models.trade import Position, Trade


class TradeService:
    def __init__(self, session: Session):
        self.session = session

    def list_trades(
        self,
        *,
        strategy_name: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[Trade]:
        statement = select(Trade)
        if strategy_name:
            statement = statement.where(Trade.strategy_name == strategy_name)
        if date_from:
            statement = statement.where(Trade.close_time >= date_from)
        if date_to:
            statement = statement.where(Trade.close_time <= date_to)
        statement = statement.order_by(desc(Trade.close_time))
        return list(self.session.exec(statement).all())

    def list_positions(self) -> list[Position]:
        statement = select(Position).where(Position.is_open.is_(True)).order_by(desc(Position.open_time))
        return list(self.session.exec(statement).all())

    def list_all_open_positions(self) -> list[Position]:
        statement = select(Position).where(Position.is_open.is_(True))
        return list(self.session.exec(statement).all())

    def get_open_position(
        self,
        instrument: str,
        strategy_name: str | None = None,
        broker_reference: str | None = None,
    ) -> Position | None:
        statement = select(Position).where(Position.is_open.is_(True))
        if broker_reference is not None:
            statement = statement.where(Position.broker_reference == broker_reference)
        else:
            statement = statement.where(Position.instrument == instrument)
        if strategy_name is not None:
            statement = statement.where(Position.strategy_name == strategy_name)
        return self.session.exec(statement).first()

    def record_trade(self, trade: Trade) -> Trade:
        self.session.add(trade)
        self.session.commit()
        self.session.refresh(trade)
        return trade

    def upsert_position(self, position: Position) -> Position:
        existing = self.get_open_position(
            position.instrument,
            strategy_name=position.strategy_name,
            broker_reference=position.broker_reference,
        )
        if existing is not None:
            for field_name in (
                "strategy_name",
                "broker_reference",
                "direction",
                "size",
                "open_price",
                "close_price",
                "open_time",
                "close_time",
                "pnl",
                "current_price",
                "unrealized_pnl",
                "risk_percent",
                "reason",
                "manual_override",
                "account_type",
                "is_open",
            ):
                setattr(existing, field_name, getattr(position, field_name))
            self.session.add(existing)
            self.session.commit()
            self.session.refresh(existing)
            return existing

        self.session.add(position)
        self.session.commit()
        self.session.refresh(position)
        return position

    def close_position(self, position: Position) -> Position:
        self.session.add(position)
        self.session.commit()
        self.session.refresh(position)
        return position
