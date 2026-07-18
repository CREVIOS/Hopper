"""Add pod_idle_state table for the idle-detection agent.

Revision ID: 013
Revises: 012
"""
from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pod_idle_state",
        sa.Column("pod_id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("pod_name", sa.String(), nullable=False),
        sa.Column("plan", sa.String(), nullable=False, server_default="small"),
        sa.Column("phase", sa.String(), nullable=False, server_default="active"),
        sa.Column("last_active_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("warned_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_pod_idle_state_user_id", "pod_idle_state", ["user_id"])
    op.create_index("ix_pod_idle_state_phase", "pod_idle_state", ["phase"])
    op.create_index("ix_pod_idle_state_last_seen_at", "pod_idle_state", ["last_seen_at"])


def downgrade() -> None:
    op.drop_index("ix_pod_idle_state_last_seen_at", table_name="pod_idle_state")
    op.drop_index("ix_pod_idle_state_phase", table_name="pod_idle_state")
    op.drop_index("ix_pod_idle_state_user_id", table_name="pod_idle_state")
    op.drop_table("pod_idle_state")
