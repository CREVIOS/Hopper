"""Add stopped_at column for billing accuracy.

Revision ID: 007
Revises: 006
Create Date: 2026-03-18 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pod_sessions", sa.Column("stopped_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("pod_sessions", "stopped_at")
