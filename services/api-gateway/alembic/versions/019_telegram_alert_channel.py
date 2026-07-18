"""Rename the WhatsApp alert columns to Telegram.

The chat alert channel moved from WhatsApp (Twilio / Green API WhatsApp) to the
Green API Telegram gateway. Delivery is still by phone number, so this is a pure
column rename — existing opt-ins carry over unchanged.

Revision ID: 019
Revises: 018
"""
from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("alert_subscriptions", "whatsapp_enabled", new_column_name="telegram_enabled")
    op.alter_column("alert_subscriptions", "whatsapp_number", new_column_name="telegram_number")


def downgrade() -> None:
    op.alter_column("alert_subscriptions", "telegram_enabled", new_column_name="whatsapp_enabled")
    op.alter_column("alert_subscriptions", "telegram_number", new_column_name="whatsapp_number")
