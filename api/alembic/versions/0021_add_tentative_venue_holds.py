"""Add tentative venue holds (SCRUM-83).

Venue Staff may place a time-limited tentative hold on a pending booking request. The
row moves to status 'tentative' and records when the hold expires, who placed it and
when. A tentative hold occupies the venue like a confirmed booking (AC3), so the ADR-0002
exclusion constraint is widened to cover both statuses. ADR-0029 records the decision.

Revision ID: 0021
Revises: 0020
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("venue_bookings", sa.Column("expires_at", sa.DateTime(timezone=True)))
    op.add_column(
        "venue_bookings", sa.Column("held_by_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column("venue_bookings", sa.Column("held_at", sa.DateTime(timezone=True)))
    op.create_foreign_key(
        "fk_venue_bookings_held_by_id_users",
        "venue_bookings",
        "users",
        ["held_by_id"],
        ["id"],
    )
    # A hold without its expiry, holder or time could block a venue forever and nobody
    # could say who placed it. The columns may stay filled after the row leaves
    # 'tentative', so that its history is kept (SCRUM-108).
    op.create_check_constraint(
        "venue_bookings_tentative_has_hold",
        "venue_bookings",
        "status <> 'tentative' OR "
        "(expires_at IS NOT NULL AND held_by_id IS NOT NULL AND held_at IS NOT NULL)",
    )

    # Same constraint name, so the code that translates its violation keeps working.
    op.drop_constraint("venue_bookings_no_confirmed_overlap", "venue_bookings")
    op.execute(
        """
        ALTER TABLE venue_bookings
        ADD CONSTRAINT venue_bookings_no_confirmed_overlap
        EXCLUDE USING gist (
            venue_id WITH =,
            tstzrange(effective_start_at, effective_end_at, '[)') WITH &&
        ) WHERE (status IN ('confirmed', 'tentative'))
        """
    )


def downgrade() -> None:
    # Before this revision a hold did not exist. A held request goes back to being a
    # plain pending request, which is what it was before the hold was placed.
    op.execute("UPDATE venue_bookings SET status = 'pending' WHERE status = 'tentative'")
    op.drop_constraint("venue_bookings_no_confirmed_overlap", "venue_bookings")
    op.execute(
        """
        ALTER TABLE venue_bookings
        ADD CONSTRAINT venue_bookings_no_confirmed_overlap
        EXCLUDE USING gist (
            venue_id WITH =,
            tstzrange(effective_start_at, effective_end_at, '[)') WITH &&
        ) WHERE (status = 'confirmed')
        """
    )
    op.drop_constraint("venue_bookings_tentative_has_hold", "venue_bookings", type_="check")
    op.drop_constraint("fk_venue_bookings_held_by_id_users", "venue_bookings", type_="foreignkey")
    op.drop_column("venue_bookings", "held_at")
    op.drop_column("venue_bookings", "held_by_id")
    op.drop_column("venue_bookings", "expires_at")
