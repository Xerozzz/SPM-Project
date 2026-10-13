"""Record each change to a venue's setup or turnaround time (SCRUM-89 AC8).

The audit half of the story. Whether a booking is problematic is derived from the venue's
current buffers whenever it is read, so nothing about that is stored; this table is the
part that must not change once written.

`flagged_booking_ids` is deliberately an array rather than a join table: it is a snapshot
of what the change caught out at the time, not a live relationship, so a foreign key would
be making a promise about the future that an audit record should not make.

Revision ID: 0019
Revises: 0018
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "venue_buffer_changes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "venue_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("venues.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "changed_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("old_setup_minutes", sa.Integer(), nullable=False),
        sa.Column("old_turnaround_minutes", sa.Integer(), nullable=False),
        sa.Column("new_setup_minutes", sa.Integer(), nullable=False),
        sa.Column("new_turnaround_minutes", sa.Integer(), nullable=False),
        sa.Column(
            "flagged_booking_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default="{}",
        ),
    )
    # The same non-negative rule the venues columns carry, so a buffer that could never
    # have been saved cannot be recorded as having been.
    op.create_check_constraint(
        "venue_buffer_changes_minutes_not_negative",
        "venue_buffer_changes",
        "old_setup_minutes >= 0 AND old_turnaround_minutes >= 0 "
        "AND new_setup_minutes >= 0 AND new_turnaround_minutes >= 0",
    )


def downgrade() -> None:
    op.drop_table("venue_buffer_changes")
