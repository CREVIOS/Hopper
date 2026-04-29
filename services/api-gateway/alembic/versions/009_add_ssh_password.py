"""Add ssh_password to pod_sessions.

Revision ID: 009
Revises: 008
Create Date: 2026-04-26 00:00:00.000000
"""

from alembic import op


revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE pod_sessions ADD COLUMN IF NOT EXISTS ssh_password VARCHAR;")


def downgrade() -> None:
    op.drop_column("pod_sessions", "ssh_password")
