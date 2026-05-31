"""Initial schema baseline.

Revision ID: 20260521_01
Revises:
Create Date: 2026-05-21 00:00:00
"""

from __future__ import annotations

from alembic import op

from app.db.schema import baseline_schema_tables, load_sqlmodel_metadata

# revision identifiers, used by Alembic.
revision = "20260521_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata = load_sqlmodel_metadata()
    metadata.create_all(op.get_bind(), tables=baseline_schema_tables())


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(baseline_schema_tables()):
        table.drop(bind, checkfirst=True)
