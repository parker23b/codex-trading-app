from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlmodel import create_engine

from app.db.migrations import alembic_config
from app.db.schema import load_sqlmodel_metadata

EXPRESSION_INDEX_NAMES = {
    "ix_allocationalert_updated_at_desc",
    "ix_allocationalert_state_updated_at",
    "ix_allocationalert_severity_updated_at",
    "ix_allocationcycle_received_at_desc",
    "ix_domain_events_category_created_at",
    "ix_domain_events_correlation_created_at",
    "ix_domain_events_created_at_desc",
    "ix_domain_events_error_type_created_at",
    "ix_domain_events_instrument_created_at",
    "ix_domain_events_severity_created_at",
    "ix_domain_events_strategy_created_at",
    "ix_observabilitystate_key_updated_desc",
    "ix_observabilitystate_scope_updated_desc",
    "ix_observabilitystate_worker_updated_desc",
    "ix_promotion_request_status_requested_at",
    "ix_runtimelease_owner_expires",
    "ix_strategy_deployment_state_strategy",
    "ix_watchlist_entry_tier_status_priority",
}


def _migrated_engine(tmp_path, db_name: str = "migrated.sqlite"):
    db_path = Path(tmp_path) / db_name
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    config = alembic_config(str(engine.url))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    return engine


def test_migrations_apply_to_empty_sqlite_database(tmp_path):
    engine = _migrated_engine(tmp_path)

    with engine.begin() as connection:
        table_names = set(
            connection.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'table'")
            ).scalars()
        )
        version = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()

    assert "tradeintent" in table_names
    assert "strategyruntimestate" in table_names
    assert "runtimelease" in table_names
    assert "observabilitystate" in table_names
    assert version == "20260529_01"


def test_migrated_schema_matches_current_sqlmodel_metadata(tmp_path):
    engine = _migrated_engine(tmp_path)
    metadata = load_sqlmodel_metadata()

    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection,
            opts={
                "compare_type": True,
                "compare_server_default": False,
                "target_metadata": metadata,
                "render_as_batch": True,
            },
        )
        diffs = compare_metadata(context, metadata)
        filtered_diffs = []
        for diff in diffs:
            kind = diff[0]
            if kind not in {"add_index", "remove_index"}:
                filtered_diffs.append(diff)
                continue
            index_name = diff[1].name
            if index_name not in EXPRESSION_INDEX_NAMES:
                filtered_diffs.append(diff)

    assert filtered_diffs == []


def test_migration_schema_enforces_active_trade_intent_uniqueness_and_runtime_modes(
    tmp_path,
):
    engine = _migrated_engine(tmp_path)

    with engine.begin() as connection:
        runtime_columns = {
            row[1]: {"notnull": int(row[3]), "default": row[4]}
            for row in connection.execute(
                text("PRAGMA table_info('strategyruntimestate')")
            ).fetchall()
        }
        tradeintent_indexes = {
            row[1]: {"unique": int(row[2]), "partial": int(row[4])}
            for row in connection.execute(
                text("PRAGMA index_list('tradeintent')")
            ).fetchall()
        }
        active_intent_index_sql = connection.execute(
            text(
                """
                SELECT sql
                FROM sqlite_master
                WHERE type = 'index' AND name = 'uq_trade_intent_active_instrument'
                """
            )
        ).scalar_one()

    assert runtime_columns["control_mode"]["notnull"] == 1
    assert runtime_columns["runtime_mode"]["notnull"] == 1
    assert runtime_columns["control_mode"]["default"] in {"'MANUAL'", '"MANUAL"'}
    assert runtime_columns["runtime_mode"]["default"] in {"'NORMAL'", '"NORMAL"'}
    assert tradeintent_indexes["uq_trade_intent_active_instrument"]["unique"] == 1
    assert tradeintent_indexes["uq_trade_intent_active_instrument"]["partial"] == 1
    assert "CLOSE_REQUESTED" in active_intent_index_sql
    assert "RECOVERED_POSITION_ATTACHED" in active_intent_index_sql
