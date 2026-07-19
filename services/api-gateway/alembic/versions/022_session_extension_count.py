"""Add pod_sessions.extension_count for session TTL extensions (FR-HC-27).

Revision ID: 022
Revises: 021
Create Date: 2026-07-19 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pod_sessions",
        sa.Column("extension_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("pod_sessions", "extension_count")
