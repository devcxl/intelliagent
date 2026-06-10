"""PR3 baseline schema

Revision ID: 0001_pr3_baseline
Revises:
Create Date: 2026-04-30 03:40:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_pr3_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False, unique=True),
        sa.Column("email", sa.String(length=255), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "conversations",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("task", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="idle"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index(
        "ix_conversations_user_updated",
        "conversations",
        ["user_id", "updated_at"],
        unique=False,
    )

    op.create_table(
        "runs",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("conversation_id", sa.String(length=64), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("max_iterations", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_runs_conversation_status", "runs", ["conversation_id", "status"], unique=False)

    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("conversation_id", sa.String(length=64), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index(
        "ix_messages_conversation_created",
        "messages",
        ["conversation_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "execution_traces",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("iteration", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index(
        "ix_execution_traces_run_iteration",
        "execution_traces",
        ["run_id", "iteration", "created_at"],
        unique=False,
    )

    op.execute(
        sa.text(
            """
            INSERT INTO users (id, username, email)
            VALUES ('local', 'anonymous', NULL)
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_execution_traces_run_iteration", table_name="execution_traces")
    op.drop_table("execution_traces")

    op.drop_index("ix_messages_conversation_created", table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_runs_conversation_status", table_name="runs")
    op.drop_table("runs")

    op.drop_index("ix_conversations_user_updated", table_name="conversations")
    op.drop_table("conversations")

    op.drop_table("users")
