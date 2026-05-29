"""Add durable observability state table.

Revision ID: 20260529_01
Revises: 20260521_01
Create Date: 2026-05-29 00:00:00
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260529_01"
down_revision = "20260521_01"
branch_labels = None
depends_on = None


UPGRADE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS observabilitystate (
        id INTEGER NOT NULL,
        state_key VARCHAR NOT NULL,
        scope_type VARCHAR NOT NULL,
        scope_id VARCHAR NOT NULL,
        worker_id VARCHAR NOT NULL,
        hostname VARCHAR NOT NULL,
        process_id INTEGER NOT NULL,
        source VARCHAR NOT NULL,
        status VARCHAR NOT NULL,
        observed_at DATETIME NOT NULL,
        expires_at DATETIME,
        payload_json JSON,
        PRIMARY KEY (id),
        CONSTRAINT uq_observabilitystate_key_scope_worker UNIQUE (state_key, scope_type, scope_id, worker_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_observabilitystate_state_key ON observabilitystate (state_key)",
    "CREATE INDEX IF NOT EXISTS ix_observabilitystate_scope_type ON observabilitystate (scope_type)",
    "CREATE INDEX IF NOT EXISTS ix_observabilitystate_scope_id ON observabilitystate (scope_id)",
    "CREATE INDEX IF NOT EXISTS ix_observabilitystate_worker_id ON observabilitystate (worker_id)",
    "CREATE INDEX IF NOT EXISTS ix_observabilitystate_hostname ON observabilitystate (hostname)",
    "CREATE INDEX IF NOT EXISTS ix_observabilitystate_process_id ON observabilitystate (process_id)",
    "CREATE INDEX IF NOT EXISTS ix_observabilitystate_source ON observabilitystate (source)",
    "CREATE INDEX IF NOT EXISTS ix_observabilitystate_status ON observabilitystate (status)",
    "CREATE INDEX IF NOT EXISTS ix_observabilitystate_observed_at ON observabilitystate (observed_at)",
    "CREATE INDEX IF NOT EXISTS ix_observabilitystate_expires_at ON observabilitystate (expires_at)",
    "CREATE INDEX IF NOT EXISTS ix_observabilitystate_key_updated_desc ON observabilitystate (state_key, observed_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_observabilitystate_scope_updated_desc ON observabilitystate (scope_type, scope_id, observed_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_observabilitystate_worker_updated_desc ON observabilitystate (worker_id, observed_at DESC)",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE observabilitystate")
