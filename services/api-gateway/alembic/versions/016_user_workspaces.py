"""Add user_workspaces table for persistent per-user workspace PVCs (FR-HC-28).

One row per user, recording the K8s PVC (name, capacity, storage class) that
backs their /workspace. The PVC is created lazily and reused across sessions;
it is never deleted by the session lifecycle.

Revision ID: 013
Revises: 012
Create Date: 2026-07-10 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_workspaces",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("pvc_name", sa.String(), nullable=False),
        sa.Column("storage_class", sa.String(), nullable=False, server_default=""),
        sa.Column("capacity_gb", sa.Integer(), nullable=False),
        sa.Column("used_gb", sa.Numeric(10, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("last_mounted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_user_workspaces_user_id"),
    )
    op.create_index("ix_user_workspaces_user_id", "user_workspaces", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_workspaces_user_id", table_name="user_workspaces")
    op.drop_table("user_workspaces")
