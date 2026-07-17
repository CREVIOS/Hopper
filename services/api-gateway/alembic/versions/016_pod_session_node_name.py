"""Record which node a VM landed on, for per-node capacity accounting.

The admission gate's aggregate capacity check (Σ free across all nodes) admits
a VM whenever the cluster as a whole has room. On a multi-node cluster that is
not sufficient: a VM must fit on some *single* node, and capacity can be
fragmented across nodes so that none does. To check per-node fit the gateway
needs to know where each live VM already sits; the orchestrator reports it on
the ``pod.started`` event and it is stored here. NULL means "not yet placed"
(reserved/creating), in which case the VM counts only toward the aggregate.

Revision ID: 016
Revises: 015
Create Date: 2026-07-17 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pod_sessions",
        sa.Column("node_name", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pod_sessions", "node_name")
