"""associate venue booking requests with their event and coordinator

SCRUM-38 turns venue_bookings from ADR-0014's search scaffold into the pending
request ledger described by ADR-0015. Every booking row now belongs to exactly
one event request and records the coordinator who submitted it, so SCRUM-40 can
decide a specific request and SCRUM-41 can later confirm the same row. The
event_request_id index supports the duplicate-pending check during submission.
Availability and overlap enforcement deliberately remain outside this migration:
search excludes unavailable venues, but SCRUM-41 owns the eventual conflict
constraint and confirmation invariant.

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("venue_bookings") as batch:
        batch.add_column(
            sa.Column("event_request_id", postgresql.UUID(as_uuid=True), nullable=False)
        )
        batch.add_column(
            sa.Column("requested_by_id", postgresql.UUID(as_uuid=True), nullable=False)
        )
        batch.create_foreign_key("fk_booking_event", "event_requests", ["event_request_id"], ["id"])
        batch.create_foreign_key("fk_booking_requester", "users", ["requested_by_id"], ["id"])
        batch.create_index("ix_venue_bookings_event_request_id", ["event_request_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("venue_bookings") as batch:
        batch.drop_index("ix_venue_bookings_event_request_id")
        batch.drop_constraint("fk_booking_requester", type_="foreignkey")
        batch.drop_constraint("fk_booking_event", type_="foreignkey")
        batch.drop_column("requested_by_id")
        batch.drop_column("event_request_id")
