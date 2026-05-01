from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlmodel import create_engine

from app.db import init_db


def test_initialize_database_adds_trade_intent_columns_to_legacy_sqlite_schema(
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
                CREATE TABLE position (
                    id INTEGER PRIMARY KEY,
                    strategy_name VARCHAR NOT NULL,
                    instrument VARCHAR NOT NULL,
                    direction VARCHAR NOT NULL,
                    size FLOAT NOT NULL,
                    open_price FLOAT NOT NULL,
                    open_time TIMESTAMP NOT NULL,
                    account_type VARCHAR NOT NULL,
                    is_open BOOLEAN NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE trade (
                    id INTEGER PRIMARY KEY,
                    strategy_name VARCHAR NOT NULL,
                    instrument VARCHAR NOT NULL,
                    direction VARCHAR NOT NULL,
                    size FLOAT NOT NULL,
                    open_price FLOAT NOT NULL,
                    close_price FLOAT NOT NULL,
                    open_time TIMESTAMP NOT NULL,
                    close_time TIMESTAMP NOT NULL,
                    account_type VARCHAR NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE execution (
                    id INTEGER PRIMARY KEY,
                    strategy_name VARCHAR NOT NULL,
                    instrument VARCHAR NOT NULL,
                    phase VARCHAR NOT NULL,
                    status VARCHAR NOT NULL,
                    signal_time TIMESTAMP NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE reconciliationevent (
                    id INTEGER PRIMARY KEY,
                    event_type VARCHAR NOT NULL,
                    strategy_name VARCHAR,
                    instrument VARCHAR,
                    broker_reference VARCHAR,
                    local_position_id INTEGER,
                    details JSON,
                    created_at TIMESTAMP
                )
                """
            )
        )

    monkeypatch.setattr(init_db, "engine", engine)

    init_db.initialize_database()

    with engine.begin() as connection:
        position_columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info('position')")
            ).fetchall()
        }
        trade_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info('trade')")).fetchall()
        }
        execution_columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info('execution')")
            ).fetchall()
        }
        reconciliation_columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info('reconciliationevent')")
            ).fetchall()
        }
        trade_intent_columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info('tradeintent')")
            ).fetchall()
        }
        allocation_alert_columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info('allocationalert')")
            ).fetchall()
        }
        indexes = {
            row[1]
            for row in connection.execute(
                text("PRAGMA index_list('tradeintent')")
            ).fetchall()
        }

    assert "trade_intent_id" in position_columns
    assert "trade_intent_id" in trade_columns
    assert "trade_intent_id" in execution_columns
    assert "trade_intent_id" in reconciliation_columns
    assert "risk_truth_confidence" in position_columns
    assert "risk_truth_confidence" in trade_columns
    assert "risk_truth_confidence" in execution_columns
    assert "allocation_cycle_id" in trade_intent_columns
    assert "estimated_risk_amount" in trade_intent_columns
    assert "risk_truth_confidence" in trade_intent_columns
    assert "alert_key" in allocation_alert_columns
    assert "state" in allocation_alert_columns
    assert "uq_trade_intent_active_instrument" in indexes
