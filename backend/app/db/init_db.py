from sqlmodel import SQLModel

from app.db.session import engine
from app.models.trade import Position, Trade


def initialize_database() -> None:
    _ = (Trade, Position)
    SQLModel.metadata.create_all(engine)
