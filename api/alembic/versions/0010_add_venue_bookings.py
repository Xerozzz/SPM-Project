"""add venue bookings

SCRUM-55: coordinator venue search must exclude venues with a confirmed booking
overlapping the requested slot, while pending requests never block. Unavailability
blocks live in the SCRUM-62 table (venue_unavailabilities, starts_at/ends_at) and are
read by repositories/venue_availability.py. The half-open overlap rule lives in
domain/venue_search.py and the repository queries it with bound parameters, so no
exclusion constraint is needed for search correctness. Status is a VARCHAR holding the
lowercase value of domain.venue_booking.BookingStatus. See ADR-0014: this table is a
search-only scaffold until SCRUM-41 owns the write path and conflict invariant.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "venue_bookings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("venue_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_venue_bookings_venue_id", "venue_bookings", ["venue_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_venue_bookings_venue_id", table_name="venue_bookings")
    op.drop_table("venue_bookings")
