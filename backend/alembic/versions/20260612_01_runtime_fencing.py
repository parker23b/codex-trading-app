"""Add runtime leadership fencing generation.

Revision ID: 20260612_01
Revises: 20260529_01
Create Date: 2026-06-12 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260612_01"
down_revision = "20260529_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("runtimelease")
    }
    if "generation" in columns:
        return

    with op.batch_alter_table("runtimelease") as batch_op:
        batch_op.add_column(
            sa.Column(
                "generation",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("1"),
            )
        )
        batch_op.alter_column("generation", server_default=None)


def downgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("runtimelease")
    }
    if "generation" not in columns:
        return

    with op.batch_alter_table("runtimelease") as batch_op:
        batch_op.drop_column("generation")
