"""Add metrics_samples hypertable for usage dashboard.

Revision ID: 008
Revises: 007
Create Date: 2026-03-18 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "metrics_samples",
        sa.Column("time", sa.DateTime(), nullable=False),
        sa.Column("pod_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False, index=True),
        sa.Column("cpu_percent", sa.Numeric(6, 2), server_default="0"),
        sa.Column("memory_used_bytes", sa.BigInteger(), server_default="0"),
        sa.Column("memory_limit_bytes", sa.BigInteger(), server_default="0"),
        sa.PrimaryKeyConstraint("time", "pod_id"),
    )
    # Convert to TimescaleDB hypertable if available
    op.execute("""
        DO $$
        BEGIN
            PERFORM create_hypertable('metrics_samples', 'time', if_not_exists => TRUE);
            PERFORM add_retention_policy('metrics_samples', INTERVAL '30 days', if_not_exists => TRUE);
        EXCEPTION WHEN undefined_function THEN
            RAISE NOTICE 'TimescaleDB not available — metrics_samples is a regular table';
        END $$;
    """)


def downgrade() -> None:
    op.drop_table("metrics_samples")
