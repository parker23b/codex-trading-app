from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session, create_engine

from app.db import init_db


def test_initialize_database_upgrades_legacy_sqlite_and_stamps_revision(
    tmp_path, monkeypatch
):
    db_path = Path(tmp_path) / "legacy.sqlite"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE strategyruntimestate (
                    id INTEGER PRIMARY KEY,
                    runtime_id VARCHAR NOT NULL,
                    strategy_name VARCHAR NOT NULL,
                    instrument VARCHAR NOT NULL,
                    status VARCHAR NOT NULL,
                    started_at TIMESTAMP NOT NULL,
                    control_mode VARCHAR,
                    runtime_mode VARCHAR,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO strategyruntimestate (
                    id,
                    runtime_id,
                    strategy_name,
                    instrument,
                    status,
                    started_at,
                    control_mode,
                    runtime_mode,
                    created_at,
                    updated_at
                )
                VALUES (
                    1,
                    'runtime-1',
                    'mean_reversion',
                    'EURUSD',
                    'STOPPED',
                    '2026-05-21 10:00:00',
                    NULL,
                    NULL,
                    '2026-05-21 10:00:00',
                    '2026-05-21 10:00:00'
                )
                """
            )
        )

    monkeypatch.setattr(init_db, "engine", engine)

    init_db.initialize_database()

    with engine.begin() as connection:
        version = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        table_names = {
            row[0]
            for row in connection.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'table'")
            ).fetchall()
        }
        runtime_columns = {
            row[1]: {"notnull": int(row[3]), "default": row[4]}
            for row in connection.execute(
                text("PRAGMA table_info('strategyruntimestate')")
            ).fetchall()
        }
        indexes = {
            row[1]
            for row in connection.execute(
                text("PRAGMA index_list('tradeintent')")
            ).fetchall()
        }

    assert version == "20260615_02"
    assert "openriskauthority" in table_names
    assert "historical_dataset" in table_names
    assert "backtest_run" in table_names
    assert "observabilitystate" in table_names
    assert runtime_columns["control_mode"]["notnull"] == 1
    assert runtime_columns["runtime_mode"]["notnull"] == 1
    assert runtime_columns["control_mode"]["default"] in {"'MANUAL'", '"MANUAL"'}
    assert runtime_columns["runtime_mode"]["default"] in {"'NORMAL'", '"NORMAL"'}
    assert "uq_trade_intent_active_instrument" in indexes

    with Session(engine) as session:
        control_mode, runtime_mode = session.exec(
            text(
                """
                SELECT control_mode, runtime_mode
                FROM strategyruntimestate
                WHERE id = 1
                """
            )
        ).one()

    assert control_mode == "MANUAL"
    assert runtime_mode == "NORMAL"
