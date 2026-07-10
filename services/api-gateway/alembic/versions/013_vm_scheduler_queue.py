"""Add vm_queue_entries and scheduler_leader for the CPU/RAM admission queue.

When the cluster is full, POST /pods/ enqueues the request as a
``vm_queue_entries`` row (state='queued') instead of creating synchronously.
A leader-elected background loop drains the queue FCFS by ``seq`` as capacity
frees. ``scheduler_leader`` is a single-row lease that keeps exactly one loop
active across uvicorn workers (pooler-safe, no advisory-lock session affinity).

Revision ID: 013
Revises: 012
Create Date: 2026-07-10 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vm_queue_entries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False, index=True),
        sa.Column("plan", sa.String(), nullable=False),
        sa.Column("template", sa.String(), nullable=False),
        sa.Column("image", sa.String(), nullable=False),
        sa.Column("cpu", sa.String(), nullable=False),
        sa.Column("memory", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False, server_default="queued"),
        sa.Column(
            "seq",
            sa.BigInteger(),
            sa.Identity(always=True, start=1),
            nullable=False,
            unique=True,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("admitted_at", sa.DateTime(), nullable=True),
        sa.Column(
            "pod_session_id",
            sa.String(),
            sa.ForeignKey("pod_sessions.id"),
            nullable=True,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
    )

    # Partial index for the FCFS admission scan: only 'queued' rows, ordered by
    # the gapless identity key. Keeps the head-of-line lookup cheap regardless
    # of how many admitted/failed rows accumulate.
    op.create_index(
        "ix_vm_queue_entries_queued_seq",
        "vm_queue_entries",
        ["seq"],
        postgresql_where=sa.text("state = 'queued'"),
    )

    op.create_table(
        "scheduler_leader",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("holder", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Seed the single lease row the admission loop contends for.
    op.execute("INSERT INTO scheduler_leader (id) VALUES ('vm-scheduler')")


def downgrade() -> None:
    op.drop_table("scheduler_leader")
    op.drop_index("ix_vm_queue_entries_queued_seq", table_name="vm_queue_entries")
    op.drop_table("vm_queue_entries")
