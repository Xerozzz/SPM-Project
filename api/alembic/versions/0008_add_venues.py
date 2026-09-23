"""add the venue catalogue

SCRUM-59: Venue Staff maintain venue records that Event Coordinators read when planning.
`is_active` carries the soft deactivation from ADR-0012: a venue is never deleted, so an
event or booking that already references it keeps a readable record.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "venues",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=False),
        sa.Column("maximum_capacity", sa.Integer(), nullable=False),
        sa.Column("facilities", postgresql.ARRAY(sa.String(length=100)), nullable=False),
        sa.Column("supported_layouts", postgresql.ARRAY(sa.String(length=50)), nullable=False),
        sa.Column(
            "accessibility_features", postgresql.ARRAY(sa.String(length=100)), nullable=False
        ),
        # Wall-clock opening hours, deliberately without a timezone: see domain/venue.py.
        sa.Column("opens_at", sa.Time(), nullable=False),
        sa.Column("closes_at", sa.Time(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_venues_name"),
    )
    # The catalogue is read far more often than it is written, and every read of the
    # selectable list filters on is_active.
    op.create_index("ix_venues_is_active", "venues", ["is_active"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_venues_is_active", table_name="venues")
    op.drop_table("venues")
