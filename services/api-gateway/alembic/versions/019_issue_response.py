"""Add issue_reports.response so admins can reply when resolving (FR-HC-29).

Revision ID: 016
Revises: 015
Create Date: 2026-07-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("issue_reports", sa.Column("response", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("issue_reports", "response")
