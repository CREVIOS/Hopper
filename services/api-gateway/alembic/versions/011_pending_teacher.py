"""Add users.pending_teacher flag.

Self-service signup lets a user request the Teacher role, but teachers must be
vetted (they later allocate credits to students). A teacher signup is created
as a `student` with pending_teacher=true; an admin approves it (promote to
professor, clear the flag) or rejects it (clear the flag, stays student).

Revision ID: 011
Revises: 010
Create Date: 2026-07-02 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "pending_teacher",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "pending_teacher")
