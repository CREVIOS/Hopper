"""Add vm_images table for admin-configurable VM templates/base images.

Seeds the four existing templates with the exact image tags previously hardcoded
in schemas/pod.py (VM_TEMPLATE_IMAGES); ubuntu is the default.

Revision ID: 018
Revises: 017
Create Date: 2026-07-18 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vm_images",
        sa.Column("template", sa.String(), primary_key=True),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("image", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    vm_images = sa.table(
        "vm_images",
        sa.column("template", sa.String),
        sa.column("display_name", sa.String),
        sa.column("image", sa.String),
        sa.column("description", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("is_default", sa.Boolean),
    )
    op.bulk_insert(
        vm_images,
        [
            {"template": "ubuntu", "display_name": "Ubuntu 22.04",
             "image": "hopper/vm-ubuntu:22.04", "description": "Base Ubuntu with SSH",
             "is_active": True, "is_default": True},
            {"template": "python-ml", "display_name": "Python / ML",
             "image": "hopper/vm-python-ml:22.04", "description": "Python 3, NumPy, Pandas, Jupyter",
             "is_active": True, "is_default": False},
            {"template": "cpp", "display_name": "C / C++",
             "image": "hopper/vm-cpp:22.04", "description": "GCC, CMake, GDB, Valgrind",
             "is_active": True, "is_default": False},
            {"template": "java", "display_name": "Java",
             "image": "hopper/vm-java:22.04", "description": "OpenJDK 21, Maven",
             "is_active": True, "is_default": False},
        ],
    )


def downgrade() -> None:
    op.drop_table("vm_images")
