from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session, create_engine

from app.core.config import Settings, get_settings
from app.db.migrations import alembic_config
from app.db.schema import load_sqlmodel_metadata
from app.db.session import get_session
from app.main import create_app
from app.models.backtest import BacktestRun
from app.services.backtest_service import (
    BACKTEST_RESULT_MANIFEST_V1,
    BacktestService,
)
from tests.migration_assertions import filtered_metadata_diffs


START = datetime(2026, 1, 1, tzinfo=UTC)


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
    assert "openriskauthority" in table_names
    assert "historical_dataset" in table_names
    assert "backtest_run" in table_names
    assert version == "20260615_02"


def test_migrated_schema_matches_current_sqlmodel_metadata(tmp_path):
    engine = _migrated_engine(tmp_path)
    metadata = load_sqlmodel_metadata()

    with engine.connect() as connection:
        filtered_diffs = filtered_metadata_diffs(connection, metadata)

    assert filtered_diffs == []


def test_backtest_result_integrity_migration_is_reversible(tmp_path):
    engine = _migrated_engine(tmp_path)
    config = alembic_config(str(engine.url))

    with engine.begin() as connection:
        run_columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info('backtest_run')")
            ).fetchall()
        }
        trade_columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info('backtest_trade')")
            ).fetchall()
        }
        warning_columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info('backtest_warning')")
            ).fetchall()
        }
    assert {"result_manifest_version", "result_checksum"}.issubset(run_columns)
    assert "deterministic_sequence" in trade_columns
    assert "deterministic_sequence" in warning_columns

    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "20260614_02")
    with engine.begin() as connection:
        run_columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info('backtest_run')")
            ).fetchall()
        }
        trade_columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info('backtest_trade')")
            ).fetchall()
        }
        warning_columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info('backtest_warning')")
            ).fetchall()
        }
    assert "result_manifest_version" not in run_columns
    assert "result_checksum" not in run_columns
    assert "deterministic_sequence" not in trade_columns
    assert "deterministic_sequence" not in warning_columns

    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def test_warmup_migration_backfills_historical_instruments_and_route_survives(
    tmp_path,
):
    engine = _migrated_engine(tmp_path, "warmup-backfill.sqlite")
    config = alembic_config(str(engine.url))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "20260615_01")
        connection.execute(
            text(
                """
                INSERT INTO backtest_run (
                    id, strategy_identifier, strategy_version,
                    strategy_configuration, dataset_id, dataset_checksum,
                    shortlist, timeframe, requested_start_at, requested_end_at,
                    starting_capital, position_sizing_mode, risk_configuration,
                    spread_model, spread_assumption, slippage_model,
                    slippage_assumption, fee_model, fee_assumption,
                    open_position_treatment, pricing_mode, evaluation_boundary,
                    status, created_at, failure_reason, result_manifest_version,
                    result_checksum, result_summary
                ) VALUES (
                    :id, 'smoke_test_hold', '1', '{}', 'legacy-dataset',
                    :dataset_checksum, '["LEGACY_FX"]', '1m', :start_at, :end_at,
                    1000, 'FIXED_UNITS', '{"fixed_size": 1}',
                    'FIXED_BPS', '{"value": 0}', 'NONE', '{"value": 0}',
                    'NONE', '{"value": 0}', 'CLOSE_AT_END',
                    'TRADE_WITH_SYNTHETIC_SPREAD', 'CANDLE_CLOSE_NEXT_OPEN',
                    'COMPLETED', :created_at, NULL, 'BACKTEST_RESULT_MANIFEST_V1',
                    :result_checksum, '{}'
                )
                """
            ),
            {
                "id": "legacy-run",
                "dataset_checksum": "a" * 64,
                "start_at": START,
                "end_at": START + timedelta(minutes=6),
                "created_at": START + timedelta(hours=1),
                "result_checksum": "b" * 64,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO backtest_run_instrument (
                    run_id, instrument, provider_instrument,
                    dataset_partition_id, candle_count, metrics
                ) VALUES (
                    'legacy-run', 'LEGACY_FX', 'LEGACY_FX', 17, 6, '{}'
                )
                """
            )
        )
        command.upgrade(config, "head")

    with engine.begin() as connection:
        first_tradable_at = connection.execute(
            text(
                """
                SELECT first_tradable_at
                FROM backtest_run_instrument
                WHERE run_id = 'legacy-run'
                """
            )
        ).scalar_one()
        instrument_columns = {
            row[1]: int(row[3])
            for row in connection.execute(
                text("PRAGMA table_info('backtest_run_instrument')")
            ).fetchall()
        }
    assert datetime.fromisoformat(str(first_tradable_at)).replace(tzinfo=UTC) == START
    assert instrument_columns["first_tradable_at"] == 1

    with Session(engine) as session:
        settings = Settings(
            **{
                **get_settings().model_dump(),
                "operator_api_credentials": {
                    "operator": {
                        "token": "expected-token",
                        "scopes": ["admin"],
                    }
                },
                "operator_api_token": None,
                "historical_data_dir": str(tmp_path / "history"),
            }
        )
        app = create_app(active_settings=settings, enable_lifespan=False)

        def override_get_session():
            yield session

        app.dependency_overrides[get_session] = override_get_session
        with TestClient(app) as client:
            response = client.get(
                "/backtests/legacy-run/instruments",
                headers={"Authorization": "Bearer expected-token"},
            )

    assert response.status_code == 200
    assert response.json()[0]["first_tradable_at"].startswith("2026-01-01T00:00:00")

    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "20260615_01")
        command.upgrade(config, "head")
        assert (
            connection.execute(
                text(
                    """
                SELECT first_tradable_at
                FROM backtest_run_instrument
                WHERE run_id = 'legacy-run'
                """
                )
            ).scalar_one()
            is not None
        )


def test_manifest_v1_verifies_before_and_after_warmup_migration_cycle(tmp_path):
    engine = _migrated_engine(tmp_path, "manifest-v1.sqlite")
    config = alembic_config(str(engine.url))
    with Session(engine) as session:
        run = BacktestRun(
            id="manifest-v1-run",
            strategy_identifier="smoke_test_hold",
            strategy_version="1",
            strategy_configuration={},
            dataset_id="historical-dataset",
            dataset_checksum="a" * 64,
            shortlist=["TEST_FX"],
            timeframe="1m",
            requested_start_at=START,
            requested_end_at=START + timedelta(minutes=6),
            warmup_start_at=START,
            trading_start_at=START,
            effective_start_at=START,
            effective_end_at=START + timedelta(minutes=6),
            starting_capital=1000,
            position_sizing_mode="FIXED_UNITS",
            risk_configuration={"fixed_size": 1},
            spread_model="FIXED_BPS",
            spread_assumption={"value": 0},
            slippage_model="NONE",
            slippage_assumption={"value": 0},
            fee_model="NONE",
            fee_assumption={"value": 0},
            open_position_treatment="CLOSE_AT_END",
            pricing_mode="TRADE_WITH_SYNTHETIC_SPREAD",
            status="COMPLETED",
            result_manifest_version=BACKTEST_RESULT_MANIFEST_V1,
        )
        session.add(run)
        session.commit()
        service = BacktestService(session)
        run.result_checksum = service.result_checksum(
            run,
            manifest_version=BACKTEST_RESULT_MANIFEST_V1,
        )
        session.add(run)
        session.commit()
        service.verify_backtest_result_checksum(run.id)

    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "20260615_01")
        command.upgrade(config, "head")

    with Session(engine) as session:
        BacktestService(session).verify_backtest_result_checksum("manifest-v1-run")


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


def test_historical_dataset_immutability_triggers_are_reversible(tmp_path):
    engine = _migrated_engine(tmp_path)
    config = alembic_config(str(engine.url))

    with engine.begin() as connection:
        trigger_names = set(
            connection.execute(
                text(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'trigger' AND name LIKE 'historical_%_guard'
                    """
                )
            ).scalars()
        )
        dataset_columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info('historical_dataset')")
            ).fetchall()
        }

    assert trigger_names == {
        "historical_dataset_ready_update_guard",
        "historical_dataset_ready_delete_guard",
        "historical_partition_ready_insert_guard",
        "historical_partition_ready_update_guard",
        "historical_partition_ready_delete_guard",
    }
    assert {
        "availability",
        "availability_reason",
        "availability_updated_at",
    }.issubset(dataset_columns)

    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "20260614_01")
    with engine.begin() as connection:
        remaining = connection.execute(
            text(
                """
                SELECT count(*)
                FROM sqlite_master
                WHERE type = 'trigger' AND name LIKE 'historical_%_guard'
                """
            )
        ).scalar_one()
        downgraded_columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info('historical_dataset')")
            ).fetchall()
        }

    assert remaining == 0
    assert "availability" not in downgraded_columns
    assert "availability_reason" not in downgraded_columns
    assert "availability_updated_at" not in downgraded_columns
