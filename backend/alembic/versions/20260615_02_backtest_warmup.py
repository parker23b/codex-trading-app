"""Add explicit backtest warm-up and trading-window truth."""

from alembic import op
import sqlalchemy as sa


revision = "20260615_02"
down_revision = "20260615_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    run_columns = {column["name"] for column in inspector.get_columns("backtest_run")}
    instrument_columns = {
        column["name"] for column in inspector.get_columns("backtest_run_instrument")
    }
    run_additions = (
        sa.Column("warmup_mode", sa.String(), nullable=False, server_default="NONE"),
        sa.Column(
            "warmup_candle_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "allow_insufficient_warmup",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("warmup_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trading_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "warmup_sufficient",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "warmup_degraded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "warmup_warnings",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    for column in run_additions:
        if column.name not in run_columns:
            op.add_column("backtest_run", column)
    op.execute(
        """
        UPDATE backtest_run
        SET warmup_start_at = requested_start_at,
            trading_start_at = requested_start_at
        """
    )
    instrument_additions = (
        sa.Column(
            "warmup_candles_consumed",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("first_tradable_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in instrument_additions:
        if column.name not in instrument_columns:
            op.add_column("backtest_run_instrument", column)
    op.execute(
        """
        UPDATE backtest_run_instrument
        SET first_tradable_at = (
            SELECT COALESCE(backtest_run.trading_start_at, backtest_run.requested_start_at)
            FROM backtest_run
            WHERE backtest_run.id = backtest_run_instrument.run_id
        )
        WHERE first_tradable_at IS NULL
        """
    )
    with op.batch_alter_table("backtest_run_instrument") as batch_op:
        batch_op.alter_column(
            "first_tradable_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )


def downgrade() -> None:
    op.drop_column("backtest_run_instrument", "first_tradable_at")
    op.drop_column("backtest_run_instrument", "warmup_candles_consumed")
    op.drop_column("backtest_run", "warmup_warnings")
    op.drop_column("backtest_run", "warmup_degraded")
    op.drop_column("backtest_run", "warmup_sufficient")
    op.drop_column("backtest_run", "trading_start_at")
    op.drop_column("backtest_run", "warmup_start_at")
    op.drop_column("backtest_run", "allow_insufficient_warmup")
    op.drop_column("backtest_run", "warmup_candle_count")
    op.drop_column("backtest_run", "warmup_mode")
