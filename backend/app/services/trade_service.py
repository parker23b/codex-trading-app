from sqlmodel import Session, desc, select

from app.models.trade import Position, Trade


class TradeService:
    def __init__(self, session: Session):
        self.session = session

    def list_trades(self) -> list[Trade]:
        statement = select(Trade).order_by(desc(Trade.open_time))
        return list(self.session.exec(statement).all())

    def list_positions(self) -> list[Position]:
        statement = select(Position).where(Position.is_open.is_(True)).order_by(desc(Position.open_time))
        return list(self.session.exec(statement).all())

    def record_trade(self, trade: Trade) -> Trade:
        self.session.add(trade)
        self.session.commit()
        self.session.refresh(trade)
        return trade

    def upsert_position(self, position: Position) -> Position:
        self.session.add(position)
        self.session.commit()
        self.session.refresh(position)
        return position

    def close_position(self, position: Position) -> Position:
        self.session.add(position)
        self.session.commit()
        self.session.refresh(position)
        return position

