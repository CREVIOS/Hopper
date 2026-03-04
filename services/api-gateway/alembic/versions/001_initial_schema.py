"""Initial schema: credit ledger, pod sessions, GPU metrics.

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Users
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(), unique=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default="student"),
        sa.Column("university_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # Credit ledger: Accounts
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=True),
        sa.Column("owner_type", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # Credit ledger: Transfers
    op.create_table(
        "transfers",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("metadata", sa.JSON(), server_default="{}"),
        sa.Column("event_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # Credit ledger: Ledger entries (double-entry)
    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("transfer_id", sa.String(), sa.ForeignKey("transfers.id"), nullable=False),
        sa.Column("account_id", sa.String(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("direction", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 4), nullable=False),
        sa.Column("previous_balance", sa.Numeric(12, 4), nullable=False),
        sa.Column("current_balance", sa.Numeric(12, 4), nullable=False),
        sa.Column("event_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_ledger_entries_account_id", "ledger_entries", ["account_id"])
    op.create_index("ix_ledger_entries_transfer_id", "ledger_entries", ["transfer_id"])

    # Prevent UPDATE/DELETE on ledger_entries (immutability)
    op.execute("""
        CREATE RULE prevent_update_ledger AS ON UPDATE TO ledger_entries
        DO INSTEAD NOTHING;
    """)
    op.execute("""
        CREATE RULE prevent_delete_ledger AS ON DELETE TO ledger_entries
        DO INSTEAD NOTHING;
    """)
    op.execute("""
        CREATE RULE prevent_update_transfers AS ON UPDATE TO transfers
        DO INSTEAD NOTHING;
    """)
    op.execute("""
        CREATE RULE prevent_delete_transfers AS ON DELETE TO transfers
        DO INSTEAD NOTHING;
    """)

    # Pod sessions
    op.create_table(
        "pod_sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False, index=True),
        sa.Column("gpu_type", sa.String(), nullable=False),
        sa.Column("namespace", sa.String(), nullable=False),
        sa.Column("pod_name", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(), server_default="pending"),
        sa.Column("credits_charged", sa.Numeric(12, 4), server_default="0"),
    )

    # GPU metrics (TimescaleDB hypertable)
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

    # Convert to hypertable (TimescaleDB)
    op.execute(
        "SELECT create_hypertable('gpu_metrics', 'time', chunk_time_interval => INTERVAL '1 hour');"
    )

    # Enable compression on gpu_metrics after 1 day
    op.execute("""
        ALTER TABLE gpu_metrics SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'node_id, gpu_index'
        );
    """)
    op.execute(
        "SELECT add_compression_policy('gpu_metrics', INTERVAL '1 day');"
    )

    # Retention policy: 30 days raw data
    op.execute(
        "SELECT add_retention_policy('gpu_metrics', INTERVAL '30 days');"
    )


def downgrade() -> None:
    op.execute("DROP RULE IF EXISTS prevent_delete_transfers ON transfers;")
    op.execute("DROP RULE IF EXISTS prevent_update_transfers ON transfers;")
    op.execute("DROP RULE IF EXISTS prevent_delete_ledger ON ledger_entries;")
    op.execute("DROP RULE IF EXISTS prevent_update_ledger ON ledger_entries;")
    op.drop_table("gpu_metrics")
    op.drop_table("pod_sessions")
    op.drop_table("ledger_entries")
    op.drop_table("transfers")
    op.drop_table("accounts")
    op.drop_table("users")
