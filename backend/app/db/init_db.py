from sqlalchemy import text
from sqlmodel import SQLModel

from app.models.allocation_alert import AllocationAlert
from app.models.domain_event import DomainEvent
from app.models.operator_control import OperatorControlState
from app.models.promotion_request import PromotionRequest
from app.models.review import GeneratedReviewRecord
from app.db.session import engine
from app.models.strategy_deployment import StrategyDeployment
from app.models.strategy_governance import StrategyFamilyGovernance
from app.models.runtime import StrategyRuntimeState
from app.models.trade import AllocationCycle, Execution, Position, ReconciliationEvent, Trade, TradeIntent
from app.models.watchlist import WatchlistEntry


def initialize_database() -> None:
    _ = (
        Trade,
        TradeIntent,
        AllocationCycle,
        AllocationAlert,
        Position,
        StrategyRuntimeState,
        ReconciliationEvent,
        Execution,
        GeneratedReviewRecord,
        DomainEvent,
        OperatorControlState,
        WatchlistEntry,
        PromotionRequest,
        StrategyFamilyGovernance,
        StrategyDeployment,
    )
    SQLModel.metadata.create_all(engine)
    _ensure_sqlite_column("position", "trade_intent_id", "INTEGER")
    _ensure_sqlite_column("position", "family_name", "VARCHAR")
    _ensure_sqlite_column("position", "broker_reference", "VARCHAR")
    _ensure_sqlite_column("position", "broker_sync_status", "VARCHAR DEFAULT 'PENDING'")
    _ensure_sqlite_column("position", "broker_open_confirmed_at", "TIMESTAMP")
    _ensure_sqlite_column("position", "broker_closed_confirmed_at", "TIMESTAMP")
    _ensure_sqlite_column("position", "last_reconciled_at", "TIMESTAMP")
    _ensure_sqlite_column("position", "entry_risk_amount", "FLOAT")
    _ensure_sqlite_column("position", "risk_truth_confidence", "VARCHAR")
    _ensure_sqlite_column("trade", "trade_intent_id", "INTEGER")
    _ensure_sqlite_column("trade", "family_name", "VARCHAR")
    _ensure_sqlite_column("trade", "broker_reference", "VARCHAR")
    _ensure_sqlite_column("trade", "close_broker_reference", "VARCHAR")
    _ensure_sqlite_column("trade", "entry_risk_amount", "FLOAT")
    _ensure_sqlite_column("trade", "risk_truth_confidence", "VARCHAR")
    _ensure_sqlite_column("execution", "trade_intent_id", "INTEGER")
    _ensure_sqlite_column("execution", "client_request_id", "VARCHAR")
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
    _ensure_sqlite_column("execution", "intended_risk_amount", "FLOAT")
    _ensure_sqlite_column("execution", "submitted_risk_amount", "FLOAT")
    _ensure_sqlite_column("execution", "fill_derived_risk_amount", "FLOAT")
    _ensure_sqlite_column("execution", "risk_truth_confidence", "VARCHAR")
    _ensure_sqlite_column("execution", "reason", "VARCHAR")
    _ensure_sqlite_column("execution", "error_code", "VARCHAR")
    _ensure_sqlite_column("execution", "error_message", "VARCHAR")
    _ensure_sqlite_column("execution", "requires_manual_review", "BOOLEAN DEFAULT 0")
    _ensure_sqlite_column("execution", "details", "JSON")
    _ensure_sqlite_column("execution", "updated_at", "TIMESTAMP")
    _ensure_sqlite_column("reconciliationevent", "trade_intent_id", "INTEGER")
    _ensure_sqlite_column("tradeintent", "family_name", "VARCHAR")
    _ensure_sqlite_column("tradeintent", "allocation_cycle_id", "VARCHAR")
    _ensure_sqlite_column("tradeintent", "estimated_risk_amount", "FLOAT")
    _ensure_sqlite_column("tradeintent", "submitted_risk_amount", "FLOAT")
    _ensure_sqlite_column("tradeintent", "fill_derived_risk_amount", "FLOAT")
    _ensure_sqlite_column("tradeintent", "risk_truth_confidence", "VARCHAR")
    _ensure_sqlite_column("tradeintent", "risk_currency", "VARCHAR")
    _ensure_index("ix_allocationalert_updated_at_desc", "allocationalert", "updated_at DESC")
    _ensure_index("ix_allocationalert_state_updated_at", "allocationalert", "state, updated_at DESC")
    _ensure_index("ix_allocationalert_severity_updated_at", "allocationalert", "severity, updated_at DESC")
    _ensure_index("ix_tradeintent_allocation_cycle_id", "tradeintent", "allocation_cycle_id")
    _ensure_sqlite_partial_unique_index(
        "uq_trade_intent_active_instrument",
        "tradeintent",
        "instrument",
        (
            "state IN ("
            "'PROPOSED', 'APPROVED', 'SUBMITTED', 'ACKNOWLEDGED', 'PARTIALLY_FILLED', "
            "'FILLED', 'POSITION_OPENED', 'CLOSE_REQUESTED', 'EXTERNAL_POSITION_ADOPTED', "
            "'RECOVERED_POSITION_ATTACHED'"
            ")"
        ),
    )
    _ensure_sqlite_column("strategyruntimestate", "strategy_version", "VARCHAR DEFAULT '1'")
    _ensure_sqlite_column("strategyruntimestate", "recovery_state", "VARCHAR DEFAULT 'PENDING'")
    _ensure_sqlite_column("strategyruntimestate", "recovery_reason", "VARCHAR")
    _ensure_sqlite_column("strategyruntimestate", "stopped_at", "TIMESTAMP")
    _ensure_sqlite_column("strategyruntimestate", "last_heartbeat_at", "TIMESTAMP")
    _ensure_sqlite_column("strategyruntimestate", "last_price_seen", "FLOAT")
    _ensure_sqlite_column("strategyruntimestate", "last_price_seen_at", "TIMESTAMP")
    _ensure_sqlite_column("strategyruntimestate", "current_position_broker_reference", "VARCHAR")
    _ensure_sqlite_column("strategyruntimestate", "control_mode", "VARCHAR DEFAULT 'MANUAL'")
    _ensure_sqlite_column("strategyruntimestate", "runtime_mode", "VARCHAR DEFAULT 'NORMAL'")
    _ensure_sqlite_column("strategyruntimestate", "deployment_id", "INTEGER")
    _ensure_sqlite_column("strategyruntimestate", "active_profile_name", "VARCHAR")
    _ensure_sqlite_column("strategyruntimestate", "auto_resume", "BOOLEAN DEFAULT 1")
    _ensure_sqlite_column("strategyruntimestate", "strategy_state_snapshot", "JSON")
    _ensure_sqlite_column("strategyruntimestate", "updated_at", "TIMESTAMP")
    _ensure_sqlite_column("strategydeployment", "open_risk_management_state", "VARCHAR DEFAULT 'NO_OPEN_RISK'")
    _ensure_sqlite_column("strategydeployment", "open_risk_management_reason", "VARCHAR")
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
    _ensure_index(
        "ix_domain_events_created_at_desc",
        "domain_events",
        "created_at DESC",
    )
    _ensure_index(
        "ix_domain_events_category_created_at",
        "domain_events",
        "category, created_at DESC",
    )
    _ensure_index(
        "ix_domain_events_strategy_created_at",
        "domain_events",
        "strategy_name, created_at DESC",
    )
    _ensure_index(
        "ix_domain_events_instrument_created_at",
        "domain_events",
        "instrument, created_at DESC",
    )
    _ensure_index(
        "ix_domain_events_severity_created_at",
        "domain_events",
        "severity, created_at DESC",
    )
    _ensure_index(
        "ix_domain_events_correlation_created_at",
        "domain_events",
        "correlation_id, created_at DESC",
    )
    _ensure_sqlite_column("domain_events", "error_type", "VARCHAR")
    _ensure_index(
        "ix_domain_events_error_type_created_at",
        "domain_events",
        "error_type, created_at DESC",
    )
    _ensure_index(
        "ix_watchlist_entry_tier_status_priority",
        "watchlist_entry",
        "tier, status, pinned DESC, priority_score DESC, assigned_at ASC",
    )
    _ensure_sqlite_column("watchlist_entry", "promotion_expires_at", "TIMESTAMP")
    _ensure_index(
        "ix_promotion_request_status_requested_at",
        "promotion_request",
        "status, requested_at DESC",
    )
    _ensure_index(
        "ix_strategy_family_governance_strategy_name",
        "strategyfamilygovernance",
        "strategy_name",
    )
    _ensure_index(
        "ix_strategy_deployment_state_strategy",
        "strategydeployment",
        "state, strategy_name, updated_at DESC",
    )
    _ensure_sqlite_column("strategydeployment", "selected_profile_parameters", "JSON")
    _ensure_sqlite_column("strategydeployment", "profile_selected_at", "TIMESTAMP")
    _ensure_sqlite_column("strategydeployment", "profile_change_reason", "VARCHAR")
    _ensure_sqlite_column("strategydeployment", "last_restart_reason", "VARCHAR")
    _ensure_index(
        "ix_allocationcycle_received_at_desc",
        "allocationcycle",
        "received_at DESC",
    )


def _ensure_sqlite_column(table_name: str, column_name: str, column_sql: str) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        rows = connection.execute(text(f"PRAGMA table_info('{table_name}')")).fetchall()
        existing_columns = {str(row[1]) for row in rows}
        if column_name in existing_columns:
            return
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"))


def _ensure_index(index_name: str, table_name: str, columns_sql: str) -> None:
    with engine.begin() as connection:
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({columns_sql})"))


def _ensure_sqlite_partial_unique_index(index_name: str, table_name: str, columns_sql: str, where_sql: str) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} "
                f"ON {table_name} ({columns_sql}) WHERE {where_sql}"
            )
        )
