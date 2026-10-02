"""forbid overlapping confirmed bookings of one venue (ADR-0002, SCRUM-74)

The database, not the application, is the authority on booking overlap: two venue staff
approving overlapping requests at the same instant can both pass the SCRUM-73 friendly
check, but only one commit can satisfy this constraint.

- `tstzrange(start_at, end_at, '[)')` is half-open, matching
  domain.venue_search.intervals_overlap: back-to-back bookings do not clash.
- `WHERE (status = 'confirmed')` matches domain.venue_search.booking_blocks_availability
  exactly (ADR-0016): pending, rejected and cancelled rows never block.
- `venue_id WITH =` needs btree_gist, enabled in revision 0001.

The range is an expression over the existing columns rather than a new `period` column,
so no data is copied and start_at/end_at stay the single source of truth. Nothing set a
booking to confirmed before this revision, so existing rows cannot violate it.
The application never wrote a confirmed row before this revision, but a
developer database may: confirming bookings by hand was the only way to test
SCRUM-55's AC4. If this revision fails locally (the api container never
starts, because docker-compose chains `alembic upgrade head && uvicorn`),
clear venue_bookings or run `docker compose down -v`.

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE venue_bookings
        ADD CONSTRAINT venue_bookings_no_confirmed_overlap
        EXCLUDE USING gist (
            venue_id WITH =,
            tstzrange(start_at, end_at, '[)') WITH &&
        ) WHERE (status = 'confirmed')
        """
    )


def downgrade() -> None:
    op.drop_constraint("venue_bookings_no_confirmed_overlap", "venue_bookings")
