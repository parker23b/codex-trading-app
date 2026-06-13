"""Add immutable historical datasets and isolated backtest results.

Revision ID: 20260614_01
Revises: 20260613_01
Create Date: 2026-06-14 00:00:00
"""

from __future__ import annotations

from alembic import op

from app.db.schema import load_sqlmodel_metadata

revision = "20260614_01"
down_revision = "20260613_01"
branch_labels = None
depends_on = None


TABLES = (
    "historical_dataset",
    "historical_dataset_partition",
    "backtest_run",
    "backtest_run_instrument",
    "backtest_trade",
    "backtest_equity_point",
    "backtest_metric",
    "backtest_warning",
)


def upgrade() -> None:
    metadata = load_sqlmodel_metadata()
    bind = op.get_bind()
    for table_name in TABLES:
        metadata.tables[table_name].create(bind, checkfirst=True)


def downgrade() -> None:
    metadata = load_sqlmodel_metadata()
    bind = op.get_bind()
    for table_name in reversed(TABLES):
        metadata.tables[table_name].drop(bind, checkfirst=True)
