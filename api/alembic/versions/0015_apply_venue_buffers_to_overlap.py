"""Apply venue setup and turnaround buffers to the overlap constraint (SCRUM-82).

A booking occupies its venue from event start minus the venue's setup time to event end
plus its turnaround time (AC3). ADR-0002 makes the database the authority on overlap, but
an exclusion constraint can only read columns of its own table, and the buffers live on
`venues`. So the effective interval is stored on the booking and the constraint moves onto
those two columns. ADR-0019 records the decision and what it costs.

The stored pair is a snapshot taken when the booking is written, deliberately not
recomputed when a venue's buffers later change: that would mean a buffer change could be
refused by this constraint, and SCRUM-89 needs the problematic state to be representable
so it can be flagged rather than refused.

Backfill is exact rather than approximate: every venue has zero buffers until SCRUM-82
part 1 lets Venue Staff set one, so effective equals the event period for every existing
row (AC7). The expression below reads the venue's values anyway, so it stays correct if
this revision is ever run against a database where part 1 landed first and buffers were
already set.

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("venue_bookings", sa.Column("effective_start_at", sa.DateTime(timezone=True)))
    op.add_column("venue_bookings", sa.Column("effective_end_at", sa.DateTime(timezone=True)))

    op.execute(
        """
        UPDATE venue_bookings AS b
        SET effective_start_at = b.start_at - make_interval(mins => v.setup_minutes),
            effective_end_at   = b.end_at   + make_interval(mins => v.turnaround_minutes)
        FROM venues AS v
        WHERE v.id = b.venue_id
        """
    )
    # Only NOT NULL after the backfill, so the revision works on a populated database.
    op.alter_column("venue_bookings", "effective_start_at", nullable=False)
    op.alter_column("venue_bookings", "effective_end_at", nullable=False)

    # The effective interval is never shorter than the event, so this holds for every row
    # the application writes and catches anything that reaches the table another way.
    op.create_check_constraint(
        "venue_bookings_effective_covers_event",
        "venue_bookings",
        "effective_start_at <= start_at AND effective_end_at >= end_at",
    )

    # Replace the SCRUM-74 constraint rather than adding a second one: two constraints on
    # overlapping definitions of the same rule is how they drift apart.
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


def downgrade() -> None:
    op.drop_constraint("venue_bookings_no_confirmed_overlap", "venue_bookings")
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
    op.drop_constraint("venue_bookings_effective_covers_event", "venue_bookings", type_="check")
    op.drop_column("venue_bookings", "effective_end_at")
    op.drop_column("venue_bookings", "effective_start_at")
