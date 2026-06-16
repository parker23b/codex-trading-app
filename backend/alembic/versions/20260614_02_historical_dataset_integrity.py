"""Protect completed historical dataset snapshots from mutation.

Revision ID: 20260614_02
Revises: 20260614_01
Create Date: 2026-06-14 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "20260614_02"
down_revision = "20260614_01"
branch_labels = None
depends_on = None


SQLITE_TRIGGERS = (
    """
    CREATE TRIGGER historical_dataset_ready_update_guard
    BEFORE UPDATE ON historical_dataset
    WHEN OLD.status = 'READY' AND (
        NEW.id IS NOT OLD.id
        OR NEW.display_name IS NOT OLD.display_name
        OR NEW.provider IS NOT OLD.provider
        OR NEW.source_identifier IS NOT OLD.source_identifier
        OR NEW.venue IS NOT OLD.venue
        OR NEW.market_type IS NOT OLD.market_type
        OR NEW.asset_class IS NOT OLD.asset_class
        OR NEW.base_timeframe IS NOT OLD.base_timeframe
        OR NEW.status IS NOT OLD.status
        OR NEW.earliest_at IS NOT OLD.earliest_at
        OR NEW.latest_at IS NOT OLD.latest_at
        OR NEW.candle_count IS NOT OLD.candle_count
        OR NEW.timezone_rule IS NOT OLD.timezone_rule
        OR NEW.price_components IS NOT OLD.price_components
        OR NEW.volume_available IS NOT OLD.volume_available
        OR NEW.imported_at IS NOT OLD.imported_at
        OR NEW.checksum IS NOT OLD.checksum
        OR NEW.completeness_status IS NOT OLD.completeness_status
        OR NEW.detected_gaps IS NOT OLD.detected_gaps
        OR NEW.warnings IS NOT OLD.warnings
        OR NEW.source_metadata IS NOT OLD.source_metadata
        OR NEW.import_parameters IS NOT OLD.import_parameters
        OR NEW.failure_reason IS NOT OLD.failure_reason
        OR NEW.storage_format IS NOT OLD.storage_format
        OR NEW.immutable IS NOT OLD.immutable
    )
    BEGIN
        SELECT RAISE(ABORT, 'ready historical datasets are immutable');
    END
    """,
    """
    CREATE TRIGGER historical_dataset_ready_delete_guard
    BEFORE DELETE ON historical_dataset
    WHEN OLD.status = 'READY'
    BEGIN
        SELECT RAISE(ABORT, 'ready historical datasets are immutable');
    END
    """,
    """
    CREATE TRIGGER historical_partition_ready_insert_guard
    BEFORE INSERT ON historical_dataset_partition
    WHEN EXISTS (
        SELECT 1
        FROM historical_dataset
        WHERE id = NEW.dataset_id AND status = 'READY'
    )
    BEGIN
        SELECT RAISE(ABORT, 'ready historical dataset partitions are immutable');
    END
    """,
    """
    CREATE TRIGGER historical_partition_ready_update_guard
    BEFORE UPDATE ON historical_dataset_partition
    WHEN
        EXISTS (
            SELECT 1
            FROM historical_dataset
            WHERE id = OLD.dataset_id AND status = 'READY'
        )
        OR EXISTS (
            SELECT 1
            FROM historical_dataset
            WHERE id = NEW.dataset_id AND status = 'READY'
        )
    BEGIN
        SELECT RAISE(ABORT, 'ready historical dataset partitions are immutable');
    END
    """,
    """
    CREATE TRIGGER historical_partition_ready_delete_guard
    BEFORE DELETE ON historical_dataset_partition
    WHEN EXISTS (
        SELECT 1
        FROM historical_dataset
        WHERE id = OLD.dataset_id AND status = 'READY'
    )
    BEGIN
        SELECT RAISE(ABORT, 'ready historical dataset partitions are immutable');
    END
    """,
)

TRIGGER_NAMES = (
    "historical_dataset_ready_update_guard",
    "historical_dataset_ready_delete_guard",
    "historical_partition_ready_insert_guard",
    "historical_partition_ready_update_guard",
    "historical_partition_ready_delete_guard",
)

UTC_COLUMNS = {
    "historical_dataset": ("earliest_at", "latest_at", "imported_at"),
    "historical_dataset_partition": ("earliest_at", "latest_at"),
    "backtest_run": (
        "requested_start_at",
        "requested_end_at",
        "effective_start_at",
        "effective_end_at",
        "created_at",
        "started_at",
        "completed_at",
    ),
    "backtest_trade": ("open_time", "close_time"),
    "backtest_equity_point": ("timestamp",),
    "backtest_warning": ("timestamp", "created_at"),
}


def upgrade() -> None:
    existing_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("historical_dataset")
    }
    availability_columns = (
        sa.Column(
            "availability",
            sa.String(),
            nullable=False,
            server_default=sa.text("'UNAVAILABLE'"),
        ),
        sa.Column("availability_reason", sa.Text(), nullable=True),
        sa.Column(
            "availability_updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    for column in availability_columns:
        if column.name not in existing_columns:
            op.add_column("historical_dataset", column)
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        for statement in SQLITE_TRIGGERS:
            op.execute(statement)
        return
    if dialect == "postgresql":
        bind = op.get_bind()
        for table_name, column_names in UTC_COLUMNS.items():
            for column_name in column_names:
                data_type = bind.execute(
                    text(
                        """
                        SELECT data_type
                        FROM information_schema.columns
                        WHERE table_schema = current_schema()
                          AND table_name = :table_name
                          AND column_name = :column_name
                        """
                    ),
                    {"table_name": table_name, "column_name": column_name},
                ).scalar_one()
                if data_type == "timestamp with time zone":
                    continue
                op.execute(
                    f"""
                    ALTER TABLE {table_name}
                    ALTER COLUMN {column_name}
                    TYPE TIMESTAMP WITH TIME ZONE
                    USING {column_name} AT TIME ZONE 'UTC'
                    """
                )
        op.execute(
            """
            CREATE FUNCTION reject_ready_historical_dataset_mutation()
            RETURNS trigger AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'ready historical datasets are immutable';
                END IF;
                IF (
                    to_jsonb(NEW)
                        - 'availability'
                        - 'availability_reason'
                        - 'availability_updated_at'
                ) IS DISTINCT FROM (
                    to_jsonb(OLD)
                        - 'availability'
                        - 'availability_reason'
                        - 'availability_updated_at'
                ) THEN
                    RAISE EXCEPTION 'ready historical datasets are immutable';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE FUNCTION reject_ready_historical_partition_mutation()
            RETURNS trigger AS $$
            BEGIN
                IF (
                    TG_OP <> 'INSERT'
                    AND EXISTS (
                        SELECT 1
                        FROM historical_dataset
                        WHERE id = OLD.dataset_id
                          AND status = 'READY'
                    )
                ) OR (
                    TG_OP <> 'DELETE'
                    AND EXISTS (
                        SELECT 1
                        FROM historical_dataset
                        WHERE id = NEW.dataset_id
                          AND status = 'READY'
                    )
                ) THEN
                    RAISE EXCEPTION
                        'ready historical dataset partitions are immutable';
                END IF;
                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER historical_dataset_ready_update_guard
            BEFORE UPDATE ON historical_dataset
            FOR EACH ROW
            WHEN (OLD.status = 'READY')
            EXECUTE FUNCTION reject_ready_historical_dataset_mutation()
            """
        )
        op.execute(
            """
            CREATE TRIGGER historical_dataset_ready_delete_guard
            BEFORE DELETE ON historical_dataset
            FOR EACH ROW
            WHEN (OLD.status = 'READY')
            EXECUTE FUNCTION reject_ready_historical_dataset_mutation()
            """
        )
        for operation in ("INSERT", "UPDATE", "DELETE"):
            op.execute(
                f"""
                CREATE TRIGGER historical_partition_ready_{operation.lower()}_guard
                BEFORE {operation} ON historical_dataset_partition
                FOR EACH ROW
                EXECUTE FUNCTION reject_ready_historical_partition_mutation()
                """
            )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        for trigger_name in reversed(TRIGGER_NAMES):
            op.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")
        with op.batch_alter_table("historical_dataset") as batch_op:
            batch_op.drop_column("availability_updated_at")
            batch_op.drop_column("availability_reason")
            batch_op.drop_column("availability")
        return
    for trigger_name in reversed(TRIGGER_NAMES):
        table_name = (
            "historical_dataset_partition"
            if "partition" in trigger_name
            else "historical_dataset"
        )
        op.execute(f"DROP TRIGGER IF EXISTS {trigger_name} ON {table_name}")
    if dialect == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS reject_ready_historical_dataset_mutation()")
        op.execute(
            "DROP FUNCTION IF EXISTS reject_ready_historical_partition_mutation()"
        )
        for table_name, column_names in reversed(tuple(UTC_COLUMNS.items())):
            for column_name in reversed(column_names):
                op.execute(
                    f"""
                    ALTER TABLE {table_name}
                    ALTER COLUMN {column_name}
                    TYPE TIMESTAMP WITHOUT TIME ZONE
                    USING {column_name} AT TIME ZONE 'UTC'
                    """
                )
    with op.batch_alter_table("historical_dataset") as batch_op:
        batch_op.drop_column("availability_updated_at")
        batch_op.drop_column("availability_reason")
        batch_op.drop_column("availability")
