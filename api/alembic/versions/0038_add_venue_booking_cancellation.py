"""Record who cancelled a venue arrangement, when and why (SCRUM-109).

The assigned Coordinator may cancel one pending request, tentative hold or confirmed
booking. The row is kept, with its decision and hold columns as they were, and gains the
cancelling Coordinator, the UTC time and the reason, all three required together once the
status is 'cancelled' (ADR-0056). Nullable, so every existing row is simply not cancelled;
no existing row is 'cancelled', because nothing set that status before this story.

The overlap exclusion constraint is not touched: since 0021 it covers only 'confirmed'
and 'tentative' rows, so a cancelled one already frees its slot, buffers included.

Revision ID: 0038
Revises: 0037
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("venue_bookings", sa.Column("cancelled_by_id", sa.UUID(), nullable=True))
    op.add_column(
        "venue_bookings", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("venue_bookings", sa.Column("cancellation_reason", sa.Text(), nullable=True))
    op.create_foreign_key(
        "venue_bookings_cancelled_by_id_fkey",
        "venue_bookings",
        "users",
        ["cancelled_by_id"],
        ["id"],
    )
    # A cancellation nobody can attribute, date or explain is not a record (AC2). Same
    # shape as venue_bookings_tentative_has_hold: the columns may only be required while
    # the row is in the status they describe.
    op.create_check_constraint(
        "venue_bookings_cancelled_has_record",
        "venue_bookings",
        "status <> 'cancelled' OR "
        "(cancelled_by_id IS NOT NULL AND cancelled_at IS NOT NULL "
        "AND cancellation_reason IS NOT NULL)",
    )


def downgrade() -> None:
    # A row cancelled under this revision stays 'cancelled' — the status existed before
    # it — but loses who, when and why, which did not exist before it either.
    op.drop_constraint("venue_bookings_cancelled_has_record", "venue_bookings", type_="check")
    op.drop_constraint("venue_bookings_cancelled_by_id_fkey", "venue_bookings", type_="foreignkey")
    op.drop_column("venue_bookings", "cancellation_reason")
    op.drop_column("venue_bookings", "cancelled_at")
    op.drop_column("venue_bookings", "cancelled_by_id")
