"""associate venue booking requests with their event and coordinator

SCRUM-38 turns venue_bookings from ADR-0014's search scaffold into the pending
request ledger described by ADR-0015. Every booking row now belongs to exactly
one event request and records the coordinator who submitted it, so SCRUM-40 can
decide a specific request and SCRUM-41 can later confirm the same row. The
event_request_id index supports the duplicate-pending check during submission.
Availability and overlap enforcement deliberately remain outside this migration:
search excludes unavailable venues, but SCRUM-41 owns the eventual conflict
constraint and confirmation invariant.

The new links are added nullable first so this revision can upgrade a non-empty
0010 database. Existing rows came from ADR-0014's search-only scaffold and have no
event or requester that can be truthfully backfilled, so they are discarded before
the columns are changed to NOT NULL. No booking-request history existed before this
revision.

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
            sa.Column("event_request_id", postgresql.UUID(as_uuid=True), nullable=True)
        )
        batch.add_column(sa.Column("requested_by_id", postgresql.UUID(as_uuid=True), nullable=True))

    # ADR-0014 rows were disposable search scaffolding, not auditable requests. Because
    # neither required link can be derived, retaining them would require fabricated data.
    op.execute(sa.text("DELETE FROM venue_bookings"))

    with op.batch_alter_table("venue_bookings") as batch:
        batch.alter_column("event_request_id", nullable=False)
        batch.alter_column("requested_by_id", nullable=False)
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
