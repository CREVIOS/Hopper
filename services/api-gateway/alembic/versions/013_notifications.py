"""Add notifications table + pod_sessions.grace_expires_at.

Notifications persist the last events a user should see (VM lifecycle,
credit warnings, credits received) and back the in-app notification
center. Rows are capped at 100 per user by the service layer — the table
is a rolling window, safe to prune.

grace_expires_at supports the credit-exhaustion grace period: instead of
killing a VM on the first failed billing tick, the gateway stamps a
deadline, warns the user, and only terminates once the deadline passes.

Revision ID: 013
Revises: 012
Create Date: 2026-07-16 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        # success | warning | error | info — maps 1:1 to toast styling.
        sa.Column("type", sa.String(), nullable=False, server_default="info"),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("body", sa.String(), nullable=False, server_default=""),
        # Structured payload for client actions (e.g. {"pod_id": ...} so a
        # "VM is ready" toast can deep-link to the VS Code button).
        sa.Column("data", postgresql.JSONB(), nullable=True),
        sa.Column("read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # The only two queries are "recent for user" and "unread count for user" —
    # one composite index serves both.
    op.create_index(
        "ix_notifications_user_created",
        "notifications",
        ["user_id", "created_at"],
    )

    op.add_column(
        "pod_sessions",
        sa.Column("grace_expires_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pod_sessions", "grace_expires_at")
    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_table("notifications")
