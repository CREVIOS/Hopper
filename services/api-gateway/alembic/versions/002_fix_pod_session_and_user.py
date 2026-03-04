"""Fix pod_sessions columns and add updated_at to users.

Revision ID: 002
Revises: 001
Create Date: 2026-03-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename gpu_type -> gpu_tier in pod_sessions
    op.alter_column("pod_sessions", "gpu_type", new_column_name="gpu_tier")

    # Rename status -> state in pod_sessions
    op.alter_column("pod_sessions", "status", new_column_name="state")

    # Add image column to pod_sessions
    op.add_column(
        "pod_sessions",
        sa.Column(
            "image",
            sa.String(),
            nullable=False,
            server_default="pytorch/pytorch:2.4.0-cuda12.4-cudnn9-runtime",
        ),
    )

    # Add updated_at to pod_sessions
    op.add_column(
        "pod_sessions",
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # Add updated_at to users
    op.add_column(
        "users",
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_column("users", "updated_at")
    op.drop_column("pod_sessions", "updated_at")
    op.drop_column("pod_sessions", "image")
    op.alter_column("pod_sessions", "state", new_column_name="status")
    op.alter_column("pod_sessions", "gpu_tier", new_column_name="gpu_type")
