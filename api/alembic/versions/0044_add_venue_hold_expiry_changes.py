"""A record of each change to a tentative hold's expiry (SCRUM-136).

SCRUM-121 overwrites `venue_bookings.expires_at` and keeps nothing else, so the old
expiry, who changed it and when were lost (the ADR-0064 gap). One row per change, written
in the same transaction as the update and never changed afterwards. Holds changed before
this migration have no rows; nothing is back-filled, because the old values are unknown.

The CHECK says a row is a change: an update to the same expiry records nothing.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "venue_hold_expiry_changes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("old_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("new_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changed_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "old_expires_at <> new_expires_at", name="venue_hold_expiry_changes_is_a_change"
        ),
        sa.ForeignKeyConstraint(["booking_id"], ["venue_bookings.id"]),
        sa.ForeignKeyConstraint(["changed_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_venue_hold_expiry_changes_booking_id", "venue_hold_expiry_changes", ["booking_id"]
    )


def downgrade() -> None:
    # The recorded changes go; each hold keeps its latest expiry, as before SCRUM-136.
    op.drop_index("ix_venue_hold_expiry_changes_booking_id", table_name="venue_hold_expiry_changes")
    op.drop_table("venue_hold_expiry_changes")
