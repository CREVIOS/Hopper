"""Add vm_plans table for admin-configurable plan resources + pricing.

Seeds the three existing plans (small/medium/large) with the exact values
previously hardcoded in schemas/pod.py, billing/types.go, and workspace_service,
so behaviour is unchanged on upgrade.

Revision ID: 017
Revises: 016
Create Date: 2026-07-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vm_plans",
        sa.Column("name", sa.String(), primary_key=True),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("cpu", sa.String(), nullable=False),
        sa.Column("memory", sa.String(), nullable=False),
        sa.Column("disk", sa.String(), nullable=False),
        sa.Column("credits_per_hour", sa.Numeric(12, 4), nullable=False),
        sa.Column("workspace_gb", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    vm_plans = sa.table(
        "vm_plans",
        sa.column("name", sa.String),
        sa.column("display_name", sa.String),
        sa.column("cpu", sa.String),
        sa.column("memory", sa.String),
        sa.column("disk", sa.String),
        sa.column("credits_per_hour", sa.Numeric),
        sa.column("workspace_gb", sa.Integer),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        vm_plans,
        [
            {"name": "small", "display_name": "Small", "cpu": "1", "memory": "2Gi",
             "disk": "5Gi", "credits_per_hour": 1.0, "workspace_gb": 20, "is_active": True},
            {"name": "medium", "display_name": "Medium", "cpu": "2", "memory": "4Gi",
             "disk": "10Gi", "credits_per_hour": 2.0, "workspace_gb": 50, "is_active": True},
            {"name": "large", "display_name": "Large", "cpu": "4", "memory": "8Gi",
             "disk": "20Gi", "credits_per_hour": 4.0, "workspace_gb": 100, "is_active": True},
        ],
    )


def downgrade() -> None:
    op.drop_table("vm_plans")
