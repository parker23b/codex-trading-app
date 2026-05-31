from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text

from app.db.schema import baseline_schema_tables, load_sqlmodel_metadata

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI_PATH = BACKEND_ROOT / "alembic.ini"
ALEMBIC_SCRIPT_PATH = BACKEND_ROOT / "alembic"
BASELINE_REVISION = "20260521_01"


def ensure_database_schema_current(engine: Engine) -> None:
    load_sqlmodel_metadata()

    with engine.connect() as connection:
        revision = _current_revision(connection)
        has_tables = _has_user_tables(connection)

    if revision is None and not has_tables:
        _run_alembic(engine, command.upgrade, "head")
        return

    if revision is not None:
        _run_alembic(engine, command.upgrade, "head")
        return

    if engine.dialect.name != "sqlite":
        raise RuntimeError(
            "Existing unversioned non-SQLite databases are not upgraded automatically. "
            "Create a fresh versioned database with Alembic and migrate data with a "
            "manual export/import or a reviewed one-off migration before starting "
            "the app."
        )

    _upgrade_legacy_sqlite_database(engine)
    _run_alembic(engine, command.stamp, BASELINE_REVISION)
    _run_alembic(engine, command.upgrade, "head")


def alembic_config(database_url: str | None = None) -> Config:
    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(ALEMBIC_SCRIPT_PATH))
    if database_url is not None:
        config.set_main_option("sqlalchemy.url", database_url)
    return config


def _run_alembic(engine: Engine, operation, *args: str) -> None:
    config = alembic_config(str(engine.url))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        operation(config, *args)


def _current_revision(connection) -> str | None:
    if "alembic_version" not in inspect(connection).get_table_names():
        return None
    return connection.execute(text("SELECT version_num FROM alembic_version")).scalar()


def _has_user_tables(connection) -> bool:
    table_names = set(inspect(connection).get_table_names())
    return bool(table_names.difference({"alembic_version"}))


def _upgrade_legacy_sqlite_database(engine: Engine) -> None:
    metadata = load_sqlmodel_metadata()
    metadata.create_all(engine, tables=baseline_schema_tables())
    _ensure_sqlite_column(engine, "position", "trade_intent_id", "INTEGER")
    _ensure_sqlite_column(engine, "position", "family_name", "VARCHAR")
    _ensure_sqlite_column(engine, "position", "broker_reference", "VARCHAR")
    _ensure_sqlite_column(
        engine, "position", "broker_sync_status", "VARCHAR DEFAULT 'PENDING'"
    )
    _ensure_sqlite_column(engine, "position", "broker_open_confirmed_at", "TIMESTAMP")
    _ensure_sqlite_column(engine, "position", "broker_closed_confirmed_at", "TIMESTAMP")
    _ensure_sqlite_column(engine, "position", "last_reconciled_at", "TIMESTAMP")
    _ensure_sqlite_column(engine, "position", "entry_risk_amount", "FLOAT")
    _ensure_sqlite_column(engine, "position", "risk_truth_confidence", "VARCHAR")
    _ensure_sqlite_column(engine, "position", "close_execution_source", "VARCHAR")
    _ensure_sqlite_column(engine, "trade", "trade_intent_id", "INTEGER")
    _ensure_sqlite_column(engine, "trade", "family_name", "VARCHAR")
    _ensure_sqlite_column(engine, "trade", "broker_reference", "VARCHAR")
    _ensure_sqlite_column(engine, "trade", "close_broker_reference", "VARCHAR")
    _ensure_sqlite_column(engine, "trade", "entry_risk_amount", "FLOAT")
    _ensure_sqlite_column(engine, "trade", "risk_truth_confidence", "VARCHAR")
    _ensure_sqlite_column(engine, "trade", "close_execution_source", "VARCHAR")
    _ensure_sqlite_column(engine, "execution", "trade_intent_id", "INTEGER")
    _ensure_sqlite_column(engine, "execution", "client_request_id", "VARCHAR")
    _ensure_sqlite_column(engine, "execution", "broker_reference", "VARCHAR")
    _ensure_sqlite_column(engine, "execution", "local_position_id", "INTEGER")
    _ensure_sqlite_column(engine, "execution", "local_trade_id", "INTEGER")
    _ensure_sqlite_column(engine, "execution", "submitted_at", "TIMESTAMP")
    _ensure_sqlite_column(engine, "execution", "acknowledged_at", "TIMESTAMP")
    _ensure_sqlite_column(engine, "execution", "completed_at", "TIMESTAMP")
    _ensure_sqlite_column(engine, "execution", "last_transition_at", "TIMESTAMP")
    _ensure_sqlite_column(engine, "execution", "requested_size", "FLOAT")
    _ensure_sqlite_column(engine, "execution", "filled_size", "FLOAT")
    _ensure_sqlite_column(engine, "execution", "requested_price", "FLOAT")
    _ensure_sqlite_column(engine, "execution", "average_fill_price", "FLOAT")
    _ensure_sqlite_column(engine, "execution", "intended_risk_amount", "FLOAT")
    _ensure_sqlite_column(engine, "execution", "submitted_risk_amount", "FLOAT")
    _ensure_sqlite_column(engine, "execution", "fill_derived_risk_amount", "FLOAT")
    _ensure_sqlite_column(engine, "execution", "risk_truth_confidence", "VARCHAR")
    _ensure_sqlite_column(engine, "execution", "reason", "VARCHAR")
    _ensure_sqlite_column(engine, "execution", "error_code", "VARCHAR")
    _ensure_sqlite_column(engine, "execution", "error_message", "VARCHAR")
    _ensure_sqlite_column(
        engine, "execution", "requires_manual_review", "BOOLEAN DEFAULT 0"
    )
    _ensure_sqlite_column(engine, "execution", "details", "JSON")
    _ensure_sqlite_column(engine, "execution", "updated_at", "TIMESTAMP")
    _ensure_sqlite_column(engine, "reconciliationevent", "trade_intent_id", "INTEGER")
    _ensure_sqlite_column(engine, "tradeintent", "family_name", "VARCHAR")
    _ensure_sqlite_column(engine, "tradeintent", "allocation_cycle_id", "VARCHAR")
    _ensure_sqlite_column(engine, "tradeintent", "estimated_risk_amount", "FLOAT")
    _ensure_sqlite_column(engine, "tradeintent", "submitted_risk_amount", "FLOAT")
    _ensure_sqlite_column(engine, "tradeintent", "fill_derived_risk_amount", "FLOAT")
    _ensure_sqlite_column(engine, "tradeintent", "risk_truth_confidence", "VARCHAR")
    _ensure_sqlite_column(engine, "tradeintent", "risk_currency", "VARCHAR")
    _ensure_sqlite_partial_unique_index(
        engine,
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
    _ensure_sqlite_column(engine, "strategyruntimestate", "strategy_version", "VARCHAR")
    _ensure_sqlite_column(engine, "strategyruntimestate", "recovery_state", "VARCHAR")
    _ensure_sqlite_column(engine, "strategyruntimestate", "recovery_reason", "VARCHAR")
    _ensure_sqlite_column(engine, "strategyruntimestate", "stopped_at", "TIMESTAMP")
    _ensure_sqlite_column(
        engine, "strategyruntimestate", "last_heartbeat_at", "TIMESTAMP"
    )
    _ensure_sqlite_column(engine, "strategyruntimestate", "last_price_seen", "FLOAT")
    _ensure_sqlite_column(
        engine, "strategyruntimestate", "last_price_seen_at", "TIMESTAMP"
    )
    _ensure_sqlite_column(
        engine, "strategyruntimestate", "current_position_broker_reference", "VARCHAR"
    )
    _ensure_sqlite_column(engine, "strategyruntimestate", "control_mode", "VARCHAR")
    _ensure_sqlite_column(engine, "strategyruntimestate", "runtime_mode", "VARCHAR")
    _ensure_sqlite_column(engine, "strategyruntimestate", "deployment_id", "INTEGER")
    _ensure_sqlite_column(
        engine, "strategyruntimestate", "active_profile_name", "VARCHAR"
    )
    _ensure_sqlite_column(engine, "strategyruntimestate", "auto_resume", "BOOLEAN")
    _ensure_sqlite_column(engine, "strategyruntimestate", "startup_context", "JSON")
    _ensure_sqlite_column(
        engine, "strategyruntimestate", "strategy_state_snapshot", "JSON"
    )
    _ensure_sqlite_column(engine, "strategyruntimestate", "updated_at", "TIMESTAMP")
    _ensure_sqlite_column(
        engine, "strategydeployment", "open_risk_management_state", "VARCHAR"
    )
    _ensure_sqlite_column(
        engine, "strategydeployment", "open_risk_management_reason", "VARCHAR"
    )
    _ensure_sqlite_column(engine, "generatedreviewrecord", "scope", "JSON")
    _ensure_sqlite_column(engine, "generatedreviewrecord", "facts_payload", "JSON")
    _ensure_sqlite_column(
        engine, "generatedreviewrecord", "derived_observations", "JSON"
    )
    _ensure_sqlite_column(
        engine, "generatedreviewrecord", "possible_contributors", "JSON"
    )
    _ensure_sqlite_column(engine, "generatedreviewrecord", "warnings", "JSON")
    _ensure_sqlite_column(engine, "generatedreviewrecord", "supporting_metrics", "JSON")
    _ensure_sqlite_column(engine, "generatedreviewrecord", "ai_summary", "JSON")
    _ensure_sqlite_column(engine, "generatedreviewrecord", "prompt_version", "VARCHAR")
    _ensure_sqlite_column(engine, "generatedreviewrecord", "provider", "VARCHAR")
    _ensure_sqlite_column(engine, "generatedreviewrecord", "model", "VARCHAR")
    _ensure_sqlite_column(engine, "generatedreviewrecord", "raw_model_response", "TEXT")
    _ensure_sqlite_column(engine, "generatedreviewrecord", "generation_mode", "VARCHAR")
    _ensure_sqlite_column(engine, "domain_events", "error_type", "VARCHAR")
    _ensure_sqlite_column(
        engine, "watchlist_entry", "promotion_expires_at", "TIMESTAMP"
    )
    _ensure_sqlite_column(
        engine, "strategydeployment", "selected_profile_parameters", "JSON"
    )
    _ensure_sqlite_column(
        engine, "strategydeployment", "profile_selected_at", "TIMESTAMP"
    )
    _ensure_sqlite_column(
        engine, "strategydeployment", "profile_change_reason", "VARCHAR"
    )
    _ensure_sqlite_column(
        engine, "strategydeployment", "last_restart_reason", "VARCHAR"
    )
    _normalize_legacy_runtime_state_schema(engine)


def _ensure_sqlite_column(
    engine: Engine, table_name: str, column_name: str, column_sql: str
) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        rows = connection.execute(text(f"PRAGMA table_info('{table_name}')")).fetchall()
        existing_columns = {str(row[1]) for row in rows}
        if column_name in existing_columns:
            return
        connection.execute(
            text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")
        )


def _ensure_sqlite_partial_unique_index(
    engine: Engine, index_name: str, table_name: str, columns_sql: str, where_sql: str
) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} "
                f"ON {table_name} ({columns_sql}) WHERE {where_sql}"
            )
        )


def _normalize_legacy_runtime_state_schema(engine: Engine) -> None:
    with engine.begin() as connection:
        columns = {
            row[1]: {"notnull": int(row[3]), "default": row[4]}
            for row in connection.execute(
                text("PRAGMA table_info('strategyruntimestate')")
            ).fetchall()
        }
        if not columns:
            return

        connection.execute(
            text(
                """
                UPDATE strategyruntimestate
                SET control_mode = COALESCE(control_mode, 'MANUAL'),
                    runtime_mode = COALESCE(runtime_mode, 'NORMAL')
                """
            )
        )

        control_mode = columns.get("control_mode")
        runtime_mode = columns.get("runtime_mode")
        if control_mode is None or runtime_mode is None:
            return

        if (
            control_mode["notnull"] == 1
            and runtime_mode["notnull"] == 1
            and control_mode["default"] in {"'MANUAL'", '"MANUAL"'}
            and runtime_mode["default"] in {"'NORMAL'", '"NORMAL"'}
        ):
            return

        def legacy_expression(column_name: str, fallback_sql: str) -> str:
            if column_name in columns:
                return column_name
            return fallback_sql

        connection.execute(
            text(
                """
                CREATE TABLE strategyruntimestate__alembic_compat (
                    id INTEGER NOT NULL PRIMARY KEY,
                    runtime_id VARCHAR NOT NULL,
                    strategy_name VARCHAR NOT NULL,
                    strategy_version VARCHAR NOT NULL,
                    instrument VARCHAR NOT NULL,
                    parameters JSON,
                    status VARCHAR NOT NULL,
                    recovery_state VARCHAR NOT NULL,
                    recovery_reason VARCHAR,
                    started_at TIMESTAMP NOT NULL,
                    stopped_at TIMESTAMP,
                    last_heartbeat_at TIMESTAMP,
                    last_price_seen FLOAT,
                    last_price_seen_at TIMESTAMP,
                    current_position_broker_reference VARCHAR,
                    control_mode VARCHAR NOT NULL DEFAULT 'MANUAL',
                    runtime_mode VARCHAR NOT NULL DEFAULT 'NORMAL',
                    deployment_id INTEGER,
                    active_profile_name VARCHAR,
                    auto_resume BOOLEAN NOT NULL,
                    startup_context JSON,
                    strategy_state_snapshot JSON,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                f"""
                INSERT INTO strategyruntimestate__alembic_compat (
                    id,
                    runtime_id,
                    strategy_name,
                    strategy_version,
                    instrument,
                    parameters,
                    status,
                    recovery_state,
                    recovery_reason,
                    started_at,
                    stopped_at,
                    last_heartbeat_at,
                    last_price_seen,
                    last_price_seen_at,
                    current_position_broker_reference,
                    control_mode,
                    runtime_mode,
                    deployment_id,
                    active_profile_name,
                    auto_resume,
                    startup_context,
                    strategy_state_snapshot,
                    created_at,
                    updated_at
                )
                SELECT
                    {legacy_expression("id", "NULL")},
                    {legacy_expression("runtime_id", "''")},
                    {legacy_expression("strategy_name", "''")},
                    COALESCE({legacy_expression("strategy_version", "NULL")}, '1'),
                    {legacy_expression("instrument", "''")},
                    {legacy_expression("parameters", "NULL")},
                    COALESCE({legacy_expression("status", "NULL")}, 'STOPPED'),
                    COALESCE({legacy_expression("recovery_state", "NULL")}, 'PENDING'),
                    {legacy_expression("recovery_reason", "NULL")},
                    COALESCE({legacy_expression("started_at", "NULL")}, {legacy_expression("created_at", "NULL")}, CURRENT_TIMESTAMP),
                    {legacy_expression("stopped_at", "NULL")},
                    {legacy_expression("last_heartbeat_at", "NULL")},
                    {legacy_expression("last_price_seen", "NULL")},
                    {legacy_expression("last_price_seen_at", "NULL")},
                    {legacy_expression("current_position_broker_reference", "NULL")},
                    COALESCE(control_mode, 'MANUAL'),
                    COALESCE(runtime_mode, 'NORMAL'),
                    {legacy_expression("deployment_id", "NULL")},
                    {legacy_expression("active_profile_name", "NULL")},
                    COALESCE({legacy_expression("auto_resume", "NULL")}, 1),
                    {legacy_expression("startup_context", "NULL")},
                    {legacy_expression("strategy_state_snapshot", "NULL")},
                    COALESCE({legacy_expression("created_at", "NULL")}, CURRENT_TIMESTAMP),
                    COALESCE({legacy_expression("updated_at", "NULL")}, CURRENT_TIMESTAMP)
                FROM strategyruntimestate
                """
            )
        )
        connection.execute(text("DROP TABLE strategyruntimestate"))
        connection.execute(
            text(
                """
                ALTER TABLE strategyruntimestate__alembic_compat
                RENAME TO strategyruntimestate
                """
            )
        )
        for statement in (
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_strategyruntimestate_runtime_id ON strategyruntimestate (runtime_id)",
            "CREATE INDEX IF NOT EXISTS ix_strategyruntimestate_strategy_name ON strategyruntimestate (strategy_name)",
            "CREATE INDEX IF NOT EXISTS ix_strategyruntimestate_instrument ON strategyruntimestate (instrument)",
            "CREATE INDEX IF NOT EXISTS ix_strategyruntimestate_status ON strategyruntimestate (status)",
            "CREATE INDEX IF NOT EXISTS ix_strategyruntimestate_recovery_state ON strategyruntimestate (recovery_state)",
            "CREATE INDEX IF NOT EXISTS ix_strategyruntimestate_current_position_broker_reference ON strategyruntimestate (current_position_broker_reference)",
            "CREATE INDEX IF NOT EXISTS ix_strategyruntimestate_control_mode ON strategyruntimestate (control_mode)",
            "CREATE INDEX IF NOT EXISTS ix_strategyruntimestate_runtime_mode ON strategyruntimestate (runtime_mode)",
            "CREATE INDEX IF NOT EXISTS ix_strategyruntimestate_deployment_id ON strategyruntimestate (deployment_id)",
            "CREATE INDEX IF NOT EXISTS ix_strategyruntimestate_active_profile_name ON strategyruntimestate (active_profile_name)",
        ):
            connection.execute(text(statement))
