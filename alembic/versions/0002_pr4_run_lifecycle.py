"""PR4 run lifecycle fields

Revision ID: 0002_pr4_run_lifecycle
Revises: 0001_pr3_baseline
Create Date: 2026-04-30 04:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_pr4_run_lifecycle"
down_revision = "0001_pr3_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("runs") as batch_op:
        batch_op.add_column(sa.Column("current_iteration", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("error", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("source_run_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("runs") as batch_op:
        batch_op.drop_column("source_run_id")
        batch_op.drop_column("cancel_requested")
        batch_op.drop_column("error")
        batch_op.drop_column("current_iteration")
