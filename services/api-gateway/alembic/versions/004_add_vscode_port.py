"""Add vscode_port to pod_sessions.

Revision ID: 004
Revises: 003
Create Date: 2026-04-17 00:00:00.000000
"""

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE pod_sessions ADD COLUMN IF NOT EXISTS vscode_port INTEGER;")


def downgrade() -> None:
    op.drop_column("pod_sessions", "vscode_port")
