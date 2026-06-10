"""PR4 single active run constraint

Revision ID: 0003_pr4_active_run_constraint
Revises: 0002_pr4_run_lifecycle
Create Date: 2026-04-30 05:35:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_pr4_active_run_constraint"
down_revision = "0002_pr4_run_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ux_runs_single_active",
        "runs",
        ["conversation_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('pending', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("ux_runs_single_active", table_name="runs")
