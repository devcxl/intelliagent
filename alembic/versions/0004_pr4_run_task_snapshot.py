"""PR4 run task snapshot

Revision ID: 0004_pr4_run_task_snapshot
Revises: 0003_pr4_active_run_constraint
Create Date: 2026-04-30 05:50:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_pr4_run_task_snapshot"
down_revision = "0003_pr4_active_run_constraint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("runs") as batch_op:
        batch_op.add_column(sa.Column("task_snapshot", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("runs") as batch_op:
        batch_op.drop_column("task_snapshot")
