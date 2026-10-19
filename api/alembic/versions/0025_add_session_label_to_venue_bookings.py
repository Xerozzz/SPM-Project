"""Add the session label to venue bookings (SCRUM-111).

One venue request is one session of its parent event, so the row carries the session's
distinguishable label. The period is already per-row (`start_at/end_at`); only the
label was missing. Pre-existing whole-event rows keep their recorded periods and are
backfilled with their event's name, falling back to 'Session' when the event is
unnamed, so no row is left without a label.

Revision ID: 0025
Revises: 0024
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("venue_bookings", sa.Column("session_label", sa.Text(), nullable=True))
    # Backfill from the parent event's name: a whole-event request made before
    # SCRUM-111 was for the whole event, so the event's name is the honest label.
    op.execute(
        """
        UPDATE venue_bookings
        SET session_label = COALESCE(
            (SELECT name FROM event_requests WHERE event_requests.id = venue_bookings.event_request_id),
            'Session'
        )
        WHERE session_label IS NULL
        """
    )
    op.alter_column("venue_bookings", "session_label", nullable=False)
    # A blank label names nothing, so refuse it where the row is written, not only in
    # the API that happens to write it today.
    op.create_check_constraint(
        "venue_bookings_session_label_nonblank",
        "venue_bookings",
        "length(trim(session_label)) > 0",
    )


def downgrade() -> None:
    op.drop_constraint("venue_bookings_session_label_nonblank", "venue_bookings")
    op.drop_column("venue_bookings", "session_label")
