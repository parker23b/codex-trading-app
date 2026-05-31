"""Add durable observability state table.

Revision ID: 20260529_01
Revises: 20260521_01
Create Date: 2026-05-29 00:00:00
"""

from __future__ import annotations

from alembic import op

from app.db.schema import observability_schema_tables

# revision identifiers, used by Alembic.
revision = "20260529_01"
down_revision = "20260521_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in observability_schema_tables():
        table.create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(observability_schema_tables()):
        table.drop(bind, checkfirst=True)
