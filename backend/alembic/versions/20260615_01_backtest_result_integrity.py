"""Add deterministic backtest result ordering and checksums.

Revision ID: 20260615_01
Revises: 20260614_02
Create Date: 2026-06-15 10:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260615_01"
down_revision = "20260614_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    run_columns = {column["name"] for column in inspector.get_columns("backtest_run")}
    trade_columns = {
        column["name"] for column in inspector.get_columns("backtest_trade")
    }
    warning_columns = {
        column["name"] for column in inspector.get_columns("backtest_warning")
    }

    if "result_manifest_version" not in run_columns:
        op.add_column(
            "backtest_run",
            sa.Column("result_manifest_version", sa.String(), nullable=True),
        )
    if "result_checksum" not in run_columns:
        op.add_column(
            "backtest_run",
            sa.Column("result_checksum", sa.String(), nullable=True),
        )
    if "deterministic_sequence" not in trade_columns:
        op.add_column(
            "backtest_trade",
            sa.Column(
                "deterministic_sequence",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )
    if "deterministic_sequence" not in warning_columns:
        op.add_column(
            "backtest_warning",
            sa.Column(
                "deterministic_sequence",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )

    index_names = {
        index["name"] for index in sa.inspect(bind).get_indexes("backtest_run")
    }
    if "ix_backtest_run_result_checksum" not in index_names:
        op.create_index(
            "ix_backtest_run_result_checksum",
            "backtest_run",
            ["result_checksum"],
        )


def downgrade() -> None:
    index_names = {
        index["name"] for index in sa.inspect(op.get_bind()).get_indexes("backtest_run")
    }
    if "ix_backtest_run_result_checksum" in index_names:
        op.drop_index(
            "ix_backtest_run_result_checksum",
            table_name="backtest_run",
        )
    with op.batch_alter_table("backtest_warning") as batch_op:
        batch_op.drop_column("deterministic_sequence")
    with op.batch_alter_table("backtest_trade") as batch_op:
        batch_op.drop_column("deterministic_sequence")
    with op.batch_alter_table("backtest_run") as batch_op:
        batch_op.drop_column("result_checksum")
        batch_op.drop_column("result_manifest_version")
