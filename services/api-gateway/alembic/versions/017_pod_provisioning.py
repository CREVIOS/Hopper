"""Add pod_provisioning table for the Smart Sandbox generator.

Revision ID: 017
Revises: 016
"""
from alembic import op
import sqlalchemy as sa

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pod_provisioning",
        sa.Column("pod_id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("provision_script", sa.Text(), nullable=False),
        sa.Column("llm_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_pod_provisioning_user_id", "pod_provisioning", ["user_id"])
    op.create_index("ix_pod_provisioning_status", "pod_provisioning", ["status"])


def downgrade() -> None:
    op.drop_index("ix_pod_provisioning_status", table_name="pod_provisioning")
    op.drop_index("ix_pod_provisioning_user_id", table_name="pod_provisioning")
    op.drop_table("pod_provisioning")
