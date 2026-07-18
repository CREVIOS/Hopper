"""Add alert_subscriptions table for per-user telemetry alert opt-in.

Revision ID: 018
Revises: 017
"""
from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_subscriptions",
        sa.Column("user_id", sa.String(), primary_key=True),
        sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("email_address", sa.String(), nullable=False, server_default=""),
        sa.Column("whatsapp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("whatsapp_number", sa.String(), nullable=False, server_default=""),
        sa.Column("min_severity", sa.String(), nullable=False, server_default="warning"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("alert_subscriptions")
