"""Add issue_reports table.

Created so students mid-session can flag a problem (SSH dropping, billing
glitch, pod eviction) without leaving the active-session view. Admins
triage from a single table instead of chasing reports across channels.

Revision ID: 010
Revises: 009
Create Date: 2026-05-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "issue_reports",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False, index=True),
        sa.Column("pod_id", sa.String(), nullable=True, index=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), index=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("issue_reports")
