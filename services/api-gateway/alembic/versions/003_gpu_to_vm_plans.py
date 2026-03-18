"""Replace GPU tiers with VM plans for resource fragmentation.

Revision ID: 003
Revises: 002
Create Date: 2026-03-14 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename gpu_tier -> plan
    op.alter_column("pod_sessions", "gpu_tier", new_column_name="plan")

    # Add cpu, memory, ssh_port columns
    op.add_column(
        "pod_sessions",
        sa.Column("cpu", sa.String(), nullable=False, server_default="1"),
    )
    op.add_column(
        "pod_sessions",
        sa.Column("memory", sa.String(), nullable=False, server_default="2Gi"),
    )
    op.add_column(
        "pod_sessions",
        sa.Column("ssh_port", sa.Integer(), nullable=True),
    )

    # Update default image from pytorch to ubuntu
    op.alter_column(
        "pod_sessions",
        "image",
        server_default="ubuntu:22.04",
    )

    # Drop gpu_metrics hypertable — no longer needed without GPUs
    op.execute("DROP TABLE IF EXISTS gpu_metrics CASCADE;")


def downgrade() -> None:
    # Recreate gpu_metrics table
    op.create_table(
        "gpu_metrics",
        sa.Column("time", sa.DateTime(), nullable=False),
        sa.Column("node_id", sa.String(), nullable=False),
        sa.Column("gpu_index", sa.Integer(), nullable=False),
        sa.Column("gpu_model", sa.String(), nullable=True),
        sa.Column("pod_id", sa.String(), nullable=True),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("gpu_utilization", sa.Float(), nullable=True),
        sa.Column("memory_used", sa.BigInteger(), nullable=True),
        sa.Column("memory_total", sa.BigInteger(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("power_usage", sa.Float(), nullable=True),
        sa.Column("sm_clock", sa.Integer(), nullable=True),
        sa.Column("mem_clock", sa.Integer(), nullable=True),
        sa.Column("pcie_errors", sa.Integer(), nullable=True),
    )

    op.alter_column("pod_sessions", "image", server_default="pytorch/pytorch:2.4.0-cuda12.4-cudnn9-runtime")
    op.drop_column("pod_sessions", "ssh_port")
    op.drop_column("pod_sessions", "memory")
    op.drop_column("pod_sessions", "cpu")
    op.alter_column("pod_sessions", "plan", new_column_name="gpu_tier")
