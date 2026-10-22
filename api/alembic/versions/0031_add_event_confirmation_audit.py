"""Record who confirmed an event and when (SCRUM-80).

AC6 asks confirmation to record its actor and time. The existing `decided_by_id` /
`decided_at` pair belongs to SCRUM-31's approve-or-reject decision on the *request*;
confirmation is a different act at a different point in the event's life, so overloading
that pair would lose which of the two a row is describing.

Nullable, like every other milestone column on this table: an event that has not been
confirmed has no confirming actor, and the status column is what says which it is.

No change to `venue_bookings`. AC4 converts a hold by moving its existing row from
'tentative' to 'confirmed', and migration 0021 already widened the ADR-0002 exclusion
constraint to cover both, so the row occupies its slot across the change and no new
constraint is needed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "event_requests",
        sa.Column("confirmed_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "event_requests",
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "event_requests_confirmed_by_id_fkey",
        "event_requests",
        "users",
        ["confirmed_by_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("event_requests_confirmed_by_id_fkey", "event_requests", type_="foreignkey")
    op.drop_column("event_requests", "confirmed_at")
    op.drop_column("event_requests", "confirmed_by_id")
