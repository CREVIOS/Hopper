"""API keys for programmatic access + VM network groups.

``api_keys`` stores scoped keys for programmatic access (HOP-19 18.1). Only
a SHA-256 hash of the secret is stored — the plaintext key is shown exactly
once at creation. ``prefix`` is the first characters of the token so users
can match a leaked/lost key against the list without us keeping the secret.

``network_group`` on pod_sessions/vm_queue_entries records the isolation
group a VM was launched into (HOP-19 18.3): VMs sharing a group get a
NetworkPolicy allowing them to reach each other; ungrouped VMs stay fully
isolated. Nullable — NULL means isolated (the default and the historic
behaviour).

Revision ID: 015
Revises: 014
Create Date: 2026-07-17 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False, index=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("prefix", sa.String(length=16), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("scope", sa.String(length=20), nullable=False, server_default="read_only"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
    )
    op.add_column("pod_sessions", sa.Column("network_group", sa.String(length=32), nullable=True))
    op.add_column(
        "vm_queue_entries", sa.Column("network_group", sa.String(length=32), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("vm_queue_entries", "network_group")
    op.drop_column("pod_sessions", "network_group")
    op.drop_table("api_keys")
