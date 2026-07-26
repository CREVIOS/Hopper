"""Add user_quotas table for per-user resource quota overrides.

No seed: absence of a row means "use the global defaults" (config).

Revision ID: 020
Revises: 019
Create Date: 2026-07-19 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_quotas",
        sa.Column("user_id", sa.String(), primary_key=True),
        sa.Column("max_concurrent_vms", sa.Integer(), nullable=False),
        sa.Column("max_workspace_gb", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("user_quotas")
