"""Add the Technical Support equipment catalogue (SCRUM-84).

Revision ID: 0018
Revises: 0017
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "equipment",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("equipment_type", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("total_quantity", sa.Integer(), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=False),
        sa.Column("operational_status", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("total_quantity >= 0", name="equipment_total_quantity_non_negative"),
        sa.CheckConstraint(
            "operational_status IN ('Operational', 'Damaged', 'Under Maintenance')",
            name="equipment_operational_status_allowed",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("equipment_type", "location", name="uq_equipment_type_location"),
    )


def downgrade() -> None:
    op.drop_table("equipment")
