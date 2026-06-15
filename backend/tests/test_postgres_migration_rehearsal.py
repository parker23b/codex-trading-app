from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from threading import Event, Thread
from time import sleep
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.engine import make_url
from sqlmodel import Session

from app.db.migrations import alembic_config, ensure_database_schema_current
from app.db.schema import load_sqlmodel_metadata
from app.models.runtime_leadership import RuntimeLease
from app.models.backtest import HistoricalDataset, HistoricalDatasetPartition
from app.services import runtime_leadership_service
from app.services.allocation_admission_lock import allocation_admission_lock
from app.services.runtime_leadership_service import (
    RuntimeLeadershipService,
    activate_runtime_leadership,
    deactivate_runtime_leadership,
    hold_active_runtime_leadership_fence,
)
from tests.migration_assertions import filtered_metadata_diffs

POSTGRES_REHEARSAL_ADMIN_URL_ENV = "POSTGRES_REHEARSAL_ADMIN_URL"

pytestmark = pytest.mark.postgres_rehearsal


def _postgres_admin_url() -> str:
    database_url = os.environ.get(POSTGRES_REHEARSAL_ADMIN_URL_ENV)
    if not database_url:
        pytest.skip(
            f"{POSTGRES_REHEARSAL_ADMIN_URL_ENV} is not set; skipping Postgres rehearsal."
        )
    return database_url


@contextmanager
def _temporary_postgres_database():
    admin_url = _postgres_admin_url()
    database_name = f"codex_migration_{uuid4().hex}"
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")

    with admin_engine.connect() as connection:
        connection.execute(text(f"CREATE DATABASE {database_name}"))

    try:
        yield (
            make_url(admin_url)
            .set(database=database_name)
            .render_as_string(hide_password=False)
        )
    finally:
        admin_engine.dispose()
        cleanup_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with cleanup_engine.connect() as connection:
            connection.execute(
                text(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = :database_name AND pid <> pg_backend_pid()
                    """
                ),
                {"database_name": database_name},
            )
            connection.execute(text(f"DROP DATABASE IF EXISTS {database_name}"))
        cleanup_engine.dispose()


def _upgrade_database(database_url: str, revision: str = "head"):
    engine = create_engine(database_url)
    config = alembic_config(database_url)
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)
    return engine


def _table_columns_by_name(engine, table_name: str) -> dict[str, dict[str, object]]:
    inspector = inspect(engine)
    return {column["name"]: column for column in inspector.get_columns(table_name)}


def _pg_indexdef(engine, *, table_name: str, index_name: str) -> str:
    with engine.connect() as connection:
        return connection.execute(
            text(
                """
                SELECT indexdef
                FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND tablename = :table_name
                  AND indexname = :index_name
                """
            ),
            {"table_name": table_name, "index_name": index_name},
        ).scalar_one()


def _pg_index_predicate(engine, *, table_name: str, index_name: str) -> str | None:
    with engine.connect() as connection:
        return connection.execute(
            text(
                """
                SELECT pg_get_expr(indexrel.indpred, indexrel.indrelid)
                FROM pg_index AS indexrel
                JOIN pg_class AS index_class ON index_class.oid = indexrel.indexrelid
                JOIN pg_class AS table_class ON table_class.oid = indexrel.indrelid
                JOIN pg_namespace AS namespace ON namespace.oid = table_class.relnamespace
                WHERE namespace.nspname = current_schema()
                  AND table_class.relname = :table_name
                  AND index_class.relname = :index_name
                """
            ),
            {"table_name": table_name, "index_name": index_name},
        ).scalar_one()


def _normalize_pg_default(raw_default: object) -> str | None:
    if raw_default is None:
        return None

    normalized = str(raw_default).strip()
    normalized = normalized.strip("()")
    for suffix in (
        "::character varying",
        "::text",
        "::bpchar",
    ):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
    if normalized.startswith("'") and normalized.endswith("'"):
        normalized = normalized[1:-1]
    return normalized


def test_postgres_migrations_apply_to_empty_database():
    with _temporary_postgres_database() as database_url:
        engine = _upgrade_database(database_url)

        try:
            inspector = inspect(engine)
            with engine.begin() as connection:
                version = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()

            assert {
                "allocationalert",
                "domain_events",
                "execution",
                "observabilitystate",
                "position",
                "runtimelease",
                "strategyruntimestate",
                "trade",
                "tradeintent",
            }.issubset(set(inspector.get_table_names()))
            assert version == "20260615_01"
        finally:
            engine.dispose()


def test_postgres_migrated_schema_matches_current_sqlmodel_metadata():
    with _temporary_postgres_database() as database_url:
        engine = _upgrade_database(database_url)
        metadata = load_sqlmodel_metadata()

        try:
            with engine.connect() as connection:
                filtered_diffs = filtered_metadata_diffs(connection, metadata)

            assert filtered_diffs == []
        finally:
            engine.dispose()


def test_postgres_ready_partition_reparenting_is_blocked_in_both_directions():
    with _temporary_postgres_database() as database_url:
        engine = _upgrade_database(database_url)
        ready_id = f"ready-{uuid4().hex}"
        mutable_id = f"mutable-{uuid4().hex}"
        now = datetime.now(UTC)

        try:
            with Session(engine) as session:
                ready = HistoricalDataset(
                    id=ready_id,
                    display_name="ready",
                    provider="CSV",
                    venue="TEST",
                    market_type="SPOT_FX",
                    asset_class="FOREX",
                    base_timeframe="1m",
                    status="IMPORTING",
                )
                mutable = HistoricalDataset(
                    id=mutable_id,
                    display_name="mutable",
                    provider="CSV",
                    venue="TEST",
                    market_type="SPOT_FX",
                    asset_class="FOREX",
                    base_timeframe="1m",
                    status="IMPORTING",
                    immutable=False,
                )
                session.add(ready)
                session.add(mutable)
                session.add(
                    HistoricalDatasetPartition(
                        dataset_id=ready_id,
                        instrument="READY_FX",
                        provider_instrument="READY_FX",
                        timeframe="1m",
                        earliest_at=now,
                        latest_at=now,
                        candle_count=1,
                        checksum="a" * 64,
                        storage_path="ready/partition.jsonl.gz",
                    )
                )
                session.add(
                    HistoricalDatasetPartition(
                        dataset_id=mutable_id,
                        instrument="MUTABLE_FX",
                        provider_instrument="MUTABLE_FX",
                        timeframe="1m",
                        earliest_at=now,
                        latest_at=now,
                        candle_count=1,
                        checksum="b" * 64,
                        storage_path="mutable/partition.jsonl.gz",
                    )
                )
                session.commit()
                ready.status = "READY"
                session.add(ready)
                session.commit()

            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        UPDATE historical_dataset
                        SET availability = 'RECOVERY_REQUIRED',
                            availability_reason = 'rehearsal recovery state',
                            availability_updated_at = :updated_at
                        WHERE id = :ready_id
                        """
                    ),
                    {"ready_id": ready_id, "updated_at": now},
                )
            with pytest.raises(DBAPIError, match="historical datasets are immutable"):
                with engine.begin() as connection:
                    connection.execute(
                        text(
                            "UPDATE historical_dataset "
                            "SET venue = 'MUTATED' WHERE id = :ready_id"
                        ),
                        {"ready_id": ready_id},
                    )

            statements = (
                (
                    "UPDATE historical_dataset_partition "
                    "SET dataset_id = :ready_id WHERE dataset_id = :mutable_id",
                    {"ready_id": ready_id, "mutable_id": mutable_id},
                ),
                (
                    "UPDATE historical_dataset_partition "
                    "SET dataset_id = :mutable_id WHERE dataset_id = :ready_id",
                    {"ready_id": ready_id, "mutable_id": mutable_id},
                ),
            )
            for statement, parameters in statements:
                with pytest.raises(DBAPIError, match="partitions are immutable"):
                    with engine.begin() as connection:
                        connection.execute(text(statement), parameters)
        finally:
            engine.dispose()


def test_postgres_schema_enforces_targeted_portability_contracts():
    with _temporary_postgres_database() as database_url:
        engine = _upgrade_database(database_url)

        try:
            inspector = inspect(engine)
            runtime_columns = _table_columns_by_name(engine, "strategyruntimestate")
            observability_columns = _table_columns_by_name(engine, "observabilitystate")
            trade_intent_columns = _table_columns_by_name(engine, "tradeintent")
            execution_columns = _table_columns_by_name(engine, "execution")
            domain_event_columns = _table_columns_by_name(engine, "domain_events")
            alert_columns = _table_columns_by_name(engine, "allocationalert")
            runtimelease_columns = _table_columns_by_name(engine, "runtimelease")

            observability_unique_constraints = {
                constraint["name"]
                for constraint in inspector.get_unique_constraints("observabilitystate")
            }

            active_intent_index = _pg_indexdef(
                engine,
                table_name="tradeintent",
                index_name="uq_trade_intent_active_instrument",
            )
            active_intent_predicate = _pg_index_predicate(
                engine,
                table_name="tradeintent",
                index_name="uq_trade_intent_active_instrument",
            )
            observability_scope_index = _pg_indexdef(
                engine,
                table_name="observabilitystate",
                index_name="ix_observabilitystate_scope_updated_desc",
            )
            runtimelease_owner_index = _pg_indexdef(
                engine,
                table_name="runtimelease",
                index_name="ix_runtimelease_owner_expires",
            )

            assert runtime_columns["control_mode"]["nullable"] is False
            assert runtime_columns["runtime_mode"]["nullable"] is False
            assert _normalize_pg_default(
                runtime_columns["control_mode"]["default"]
            ) == ("MANUAL")
            assert _normalize_pg_default(
                runtime_columns["runtime_mode"]["default"]
            ) == ("NORMAL")

            assert trade_intent_columns["state"]["nullable"] is False
            assert execution_columns["status"]["nullable"] is False
            assert domain_event_columns["event_type"]["nullable"] is False
            assert alert_columns["alert_key"]["nullable"] is False
            assert runtimelease_columns["lease_name"]["nullable"] is False
            assert runtimelease_columns["owner_id"]["nullable"] is False
            assert runtimelease_columns["generation"]["nullable"] is False
            assert runtimelease_columns["expires_at"]["nullable"] is False
            assert observability_columns["state_key"]["nullable"] is False
            assert observability_columns["scope_type"]["nullable"] is False
            assert observability_columns["scope_id"]["nullable"] is False
            assert observability_columns["worker_id"]["nullable"] is False
            assert observability_columns["hostname"]["nullable"] is False
            assert observability_columns["process_id"]["nullable"] is False
            assert observability_columns["source"]["nullable"] is False
            assert observability_columns["status"]["nullable"] is False
            assert observability_columns["observed_at"]["nullable"] is False

            assert "uq_observabilitystate_key_scope_worker" in (
                observability_unique_constraints
            )
            assert "WHERE " in active_intent_index
            assert active_intent_predicate is not None
            assert "PROPOSED" in active_intent_predicate
            assert "CLOSE_REQUESTED" in active_intent_predicate
            assert "RECOVERED_POSITION_ATTACHED" in active_intent_index
            assert "observed_at DESC" in observability_scope_index
            assert "expires_at DESC" in runtimelease_owner_index
        finally:
            engine.dispose()


def test_postgres_versioned_upgrade_rehearses_baseline_to_head_transition():
    with _temporary_postgres_database() as database_url:
        engine = _upgrade_database(database_url, "20260521_01")

        try:
            inspector = inspect(engine)
            with engine.begin() as connection:
                version = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()

            assert version == "20260521_01"
            assert "observabilitystate" not in inspector.get_table_names()
        finally:
            engine.dispose()

        engine = _upgrade_database(database_url, "head")

        try:
            inspector = inspect(engine)
            with engine.begin() as connection:
                version = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()

            assert version == "20260615_01"
            assert "observabilitystate" in inspector.get_table_names()
        finally:
            engine.dispose()


def test_postgres_refuses_unversioned_legacy_database_without_auto_stamp():
    with _temporary_postgres_database() as database_url:
        engine = create_engine(database_url)

        try:
            with engine.begin() as connection:
                connection.execute(
                    text("CREATE TABLE legacy_probe (id INTEGER PRIMARY KEY)")
                )

            with pytest.raises(RuntimeError, match="not upgraded automatically"):
                ensure_database_schema_current(engine)

            assert "alembic_version" not in inspect(engine).get_table_names()
        finally:
            engine.dispose()


def test_postgres_allocation_admission_lock_serializes_distinct_connections():
    with _temporary_postgres_database() as database_url:
        engine = _upgrade_database(database_url)
        first_entered = Event()
        release_first = Event()
        second_attempting = Event()
        order: list[str] = []
        errors: list[BaseException] = []

        def first_worker():
            try:
                with Session(engine) as session:
                    with allocation_admission_lock(session):
                        order.append("first")
                        first_entered.set()
                        assert release_first.wait(timeout=5)
            except BaseException as exc:
                errors.append(exc)

        def second_worker():
            try:
                assert first_entered.wait(timeout=5)
                with Session(engine) as session:
                    second_attempting.set()
                    with allocation_admission_lock(session):
                        order.append("second")
            except BaseException as exc:
                errors.append(exc)

        first = Thread(target=first_worker)
        second = Thread(target=second_worker)
        first.start()
        second.start()
        assert second_attempting.wait(timeout=5)
        sleep(0.2)

        assert order == ["first"]

        release_first.set()
        first.join(timeout=5)
        second.join(timeout=5)
        assert not first.is_alive()
        assert not second.is_alive()
        engine.dispose()

        assert errors == []
        assert order == ["first", "second"]


def test_postgres_runtime_fence_blocks_takeover_until_mutation_finishes(monkeypatch):
    with _temporary_postgres_database() as database_url:
        engine = _upgrade_database(database_url)
        now = datetime.now(UTC)
        with Session(engine) as session:
            acquisition = RuntimeLeadershipService(
                session,
                owner_id="worker-a",
            ).acquire(now=now, ttl=timedelta(seconds=30))

        assert acquisition.generation == 1
        monkeypatch.setattr(runtime_leadership_service, "engine", engine)
        activate_runtime_leadership(
            owner_id="worker-a",
            generation=acquisition.generation,
        )
        fence_entered = Event()
        release_fence = Event()
        takeover_attempting = Event()
        takeover_results = []
        errors: list[BaseException] = []

        def fenced_mutation():
            try:
                with hold_active_runtime_leadership_fence():
                    fence_entered.set()
                    assert release_fence.wait(timeout=5)
            except BaseException as exc:
                errors.append(exc)

        def takeover_worker():
            try:
                assert fence_entered.wait(timeout=5)
                takeover_attempting.set()
                with Session(engine) as session:
                    takeover_results.append(
                        RuntimeLeadershipService(
                            session,
                            owner_id="worker-b",
                        ).acquire(
                            now=now + timedelta(seconds=31),
                            ttl=timedelta(seconds=30),
                        )
                    )
            except BaseException as exc:
                errors.append(exc)

        mutation = Thread(target=fenced_mutation)
        takeover = Thread(target=takeover_worker)
        mutation.start()
        takeover.start()
        assert takeover_attempting.wait(timeout=5)
        sleep(0.2)

        assert takeover_results == []

        release_fence.set()
        mutation.join(timeout=5)
        takeover.join(timeout=5)
        assert not mutation.is_alive()
        assert not takeover.is_alive()

        try:
            assert errors == []
            assert len(takeover_results) == 1
            assert takeover_results[0].acquired is True
            assert takeover_results[0].generation == 2
            with Session(engine) as session:
                lease = session.get(
                    RuntimeLease,
                    RuntimeLeadershipService.RUNTIME_LEASE_NAME,
                )
            assert lease is not None
            assert lease.owner_id == "worker-b"
            assert lease.generation == 2
        finally:
            deactivate_runtime_leadership(
                owner_id="worker-a",
                generation=acquisition.generation,
            )
            engine.dispose()
