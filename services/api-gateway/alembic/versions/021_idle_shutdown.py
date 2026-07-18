"""Add pod_sessions.idle_shutdown_at for idle auto-shutdown.

Revision ID: 021
Revises: 020
Create Date: 2026-07-19 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pod_sessions",
        sa.Column("idle_shutdown_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_pod_sessions_idle_shutdown_at", "pod_sessions", ["idle_shutdown_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_pod_sessions_idle_shutdown_at", table_name="pod_sessions")
    op.drop_column("pod_sessions", "idle_shutdown_at")
