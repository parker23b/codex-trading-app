"""Add the versioned open-risk authority aggregate.

Revision ID: 20260613_01
Revises: 20260612_01
Create Date: 2026-06-13 00:00:00
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op

from app.db.schema import load_sqlmodel_metadata

revision = "20260613_01"
down_revision = "20260612_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata = load_sqlmodel_metadata()
    authority_table = metadata.tables["openriskauthority"]
    authority_table.create(op.get_bind(), checkfirst=True)
    op.bulk_insert(
        authority_table,
        [
            {
                "scope_key": "primary",
                "version": 1,
                "state": "NO_OPEN_RISK",
                "reason": "No local open positions.",
                "open_position_count": 0,
                "reconciliation_status": "UNKNOWN",
                "last_reconciled_at": None,
                "snapshot_json": {},
                "updated_at": datetime.now(timezone.utc),
            }
        ],
    )


def downgrade() -> None:
    metadata = load_sqlmodel_metadata()
    metadata.tables["openriskauthority"].drop(op.get_bind(), checkfirst=True)
