from sqlalchemy import text
from sqlmodel import SQLModel

from app.db.session import engine
from app.models.runtime import StrategyRuntimeState
from app.models.trade import Position, ReconciliationEvent, Trade


def initialize_database() -> None:
    _ = (Trade, Position, StrategyRuntimeState, ReconciliationEvent)
    SQLModel.metadata.create_all(engine)
    _ensure_sqlite_column("position", "broker_reference", "VARCHAR")
    _ensure_sqlite_column("position", "broker_sync_status", "VARCHAR DEFAULT 'PENDING'")
    _ensure_sqlite_column("position", "broker_open_confirmed_at", "TIMESTAMP")
    _ensure_sqlite_column("position", "broker_closed_confirmed_at", "TIMESTAMP")
    _ensure_sqlite_column("position", "last_reconciled_at", "TIMESTAMP")
    _ensure_sqlite_column("trade", "broker_reference", "VARCHAR")
    _ensure_sqlite_column("trade", "close_broker_reference", "VARCHAR")
    _ensure_sqlite_column("strategyruntimestate", "strategy_version", "VARCHAR DEFAULT '1'")
    _ensure_sqlite_column("strategyruntimestate", "recovery_state", "VARCHAR DEFAULT 'PENDING'")
    _ensure_sqlite_column("strategyruntimestate", "recovery_reason", "VARCHAR")
    _ensure_sqlite_column("strategyruntimestate", "stopped_at", "TIMESTAMP")
    _ensure_sqlite_column("strategyruntimestate", "last_heartbeat_at", "TIMESTAMP")
    _ensure_sqlite_column("strategyruntimestate", "last_price_seen", "FLOAT")
    _ensure_sqlite_column("strategyruntimestate", "last_price_seen_at", "TIMESTAMP")
    _ensure_sqlite_column("strategyruntimestate", "current_position_broker_reference", "VARCHAR")
    _ensure_sqlite_column("strategyruntimestate", "auto_resume", "BOOLEAN DEFAULT 1")
    _ensure_sqlite_column("strategyruntimestate", "strategy_state_snapshot", "JSON")
    _ensure_sqlite_column("strategyruntimestate", "updated_at", "TIMESTAMP")


def _ensure_sqlite_column(table_name: str, column_name: str, column_sql: str) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        rows = connection.execute(text(f"PRAGMA table_info('{table_name}')")).fetchall()
        existing_columns = {str(row[1]) for row in rows}
        if column_name in existing_columns:
            return
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"))
