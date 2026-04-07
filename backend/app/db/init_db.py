from sqlalchemy import text
from sqlmodel import SQLModel

from app.models.review import GeneratedReviewRecord
from app.db.session import engine
from app.models.runtime import StrategyRuntimeState
from app.models.trade import Execution, Position, ReconciliationEvent, Trade


def initialize_database() -> None:
    _ = (Trade, Position, StrategyRuntimeState, ReconciliationEvent, Execution, GeneratedReviewRecord)
    SQLModel.metadata.create_all(engine)
    _ensure_sqlite_column("position", "broker_reference", "VARCHAR")
    _ensure_sqlite_column("position", "broker_sync_status", "VARCHAR DEFAULT 'PENDING'")
    _ensure_sqlite_column("position", "broker_open_confirmed_at", "TIMESTAMP")
    _ensure_sqlite_column("position", "broker_closed_confirmed_at", "TIMESTAMP")
    _ensure_sqlite_column("position", "last_reconciled_at", "TIMESTAMP")
    _ensure_sqlite_column("trade", "broker_reference", "VARCHAR")
    _ensure_sqlite_column("trade", "close_broker_reference", "VARCHAR")
    _ensure_sqlite_column("execution", "broker_reference", "VARCHAR")
    _ensure_sqlite_column("execution", "local_position_id", "INTEGER")
    _ensure_sqlite_column("execution", "local_trade_id", "INTEGER")
    _ensure_sqlite_column("execution", "submitted_at", "TIMESTAMP")
    _ensure_sqlite_column("execution", "acknowledged_at", "TIMESTAMP")
    _ensure_sqlite_column("execution", "completed_at", "TIMESTAMP")
    _ensure_sqlite_column("execution", "last_transition_at", "TIMESTAMP")
    _ensure_sqlite_column("execution", "requested_size", "FLOAT")
    _ensure_sqlite_column("execution", "filled_size", "FLOAT")
    _ensure_sqlite_column("execution", "requested_price", "FLOAT")
    _ensure_sqlite_column("execution", "average_fill_price", "FLOAT")
    _ensure_sqlite_column("execution", "reason", "VARCHAR")
    _ensure_sqlite_column("execution", "error_code", "VARCHAR")
    _ensure_sqlite_column("execution", "error_message", "VARCHAR")
    _ensure_sqlite_column("execution", "requires_manual_review", "BOOLEAN DEFAULT 0")
    _ensure_sqlite_column("execution", "details", "JSON")
    _ensure_sqlite_column("execution", "updated_at", "TIMESTAMP")
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
    _ensure_sqlite_column("generatedreviewrecord", "scope", "JSON")
    _ensure_sqlite_column("generatedreviewrecord", "facts_payload", "JSON")
    _ensure_sqlite_column("generatedreviewrecord", "derived_observations", "JSON")
    _ensure_sqlite_column("generatedreviewrecord", "possible_contributors", "JSON")
    _ensure_sqlite_column("generatedreviewrecord", "warnings", "JSON")
    _ensure_sqlite_column("generatedreviewrecord", "supporting_metrics", "JSON")
    _ensure_sqlite_column("generatedreviewrecord", "ai_summary", "JSON")
    _ensure_sqlite_column("generatedreviewrecord", "prompt_version", "VARCHAR DEFAULT 'ai-reviewer-v1'")
    _ensure_sqlite_column("generatedreviewrecord", "provider", "VARCHAR")
    _ensure_sqlite_column("generatedreviewrecord", "model", "VARCHAR")
    _ensure_sqlite_column("generatedreviewrecord", "raw_model_response", "TEXT")
    _ensure_sqlite_column("generatedreviewrecord", "generation_mode", "VARCHAR DEFAULT 'deterministic_only'")


def _ensure_sqlite_column(table_name: str, column_name: str, column_sql: str) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        rows = connection.execute(text(f"PRAGMA table_info('{table_name}')")).fetchall()
        existing_columns = {str(row[1]) for row in rows}
        if column_name in existing_columns:
            return
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"))
