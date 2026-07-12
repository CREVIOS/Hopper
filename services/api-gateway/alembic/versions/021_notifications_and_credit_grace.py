"""Add notifications table + pod_sessions.credit_grace_until (FR-HC-18).

Ported from the feature/notifications-credit-alerts branch, which authored this
as revision "011" and collided with 011_pending_teacher on main. Renumbered onto
the current head (020_courses).

Revision ID: 021
Revises: 020
Create Date: 2026-07-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("action_url", sa.String(), nullable=True),
        sa.Column("dedupe_key", sa.String(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        # One row per (user, dedupe_key) so a warning band fires at most once per
        # VM — the billing tick runs every minute and would otherwise spam.
        sa.UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_read_at", "notifications", ["read_at"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])

    op.add_column(
        "pod_sessions",
        sa.Column("credit_grace_until", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_pod_sessions_credit_grace_until", "pod_sessions", ["credit_grace_until"]
    )


def downgrade() -> None:
    op.drop_index("ix_pod_sessions_credit_grace_until", table_name="pod_sessions")
    op.drop_column("pod_sessions", "credit_grace_until")
    op.drop_table("notifications")
