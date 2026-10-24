"""Record who adopted a replacement venue request and when (SCRUM-133).

Set on the replacement row when the assigned Coordinator adopts it and the original is
cancelled through SCRUM-109. Only a replacement can be adopted, and actor and time go
together (ADR-0057). Nullable, so every existing row is simply not adopted.

Revision ID: 0039
Revises: 0038
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("venue_bookings", sa.Column("adopted_by_id", sa.UUID(), nullable=True))
    op.add_column(
        "venue_bookings", sa.Column("adopted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        "venue_bookings_adopted_by_id_fkey", "venue_bookings", "users", ["adopted_by_id"], ["id"]
    )
    op.create_check_constraint(
        "venue_bookings_adoption_is_complete",
        "venue_bookings",
        "(adopted_at IS NULL AND adopted_by_id IS NULL) OR "
        "(adopted_at IS NOT NULL AND adopted_by_id IS NOT NULL "
        "AND replaces_booking_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("venue_bookings_adoption_is_complete", "venue_bookings", type_="check")
    op.drop_constraint("venue_bookings_adopted_by_id_fkey", "venue_bookings", type_="foreignkey")
    op.drop_column("venue_bookings", "adopted_at")
    op.drop_column("venue_bookings", "adopted_by_id")
