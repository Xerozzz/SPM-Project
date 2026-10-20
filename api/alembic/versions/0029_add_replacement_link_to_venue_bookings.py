"""Link a replacement venue request to the arrangement it replaces (SCRUM-116).

Nullable, so every existing request is simply not a replacement (ADR-0045).

Revision ID: 0029
Revises: 0028
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("venue_bookings", sa.Column("replaces_booking_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "venue_bookings_replaces_booking_id_fkey",
        "venue_bookings",
        "venue_bookings",
        ["replaces_booking_id"],
        ["id"],
    )
    op.create_index(
        "ix_venue_bookings_replaces_booking_id", "venue_bookings", ["replaces_booking_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_venue_bookings_replaces_booking_id", table_name="venue_bookings")
    op.drop_constraint(
        "venue_bookings_replaces_booking_id_fkey", "venue_bookings", type_="foreignkey"
    )
    op.drop_column("venue_bookings", "replaces_booking_id")
