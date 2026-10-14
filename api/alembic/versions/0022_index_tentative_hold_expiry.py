"""Index tentative holds by expiry (SCRUM-108).

The minute timer and every hold or approval look for tentative holds whose expiry has
passed. A partial index over just those rows keeps that lookup small however many
bookings the table holds. ADR-0030.

Revision ID: 0022
Revises: 0021
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_venue_bookings_tentative_expires_at",
        "venue_bookings",
        ["expires_at"],
        postgresql_where=sa.text("status = 'tentative'"),
    )


def downgrade() -> None:
    # Expired holds did not exist before this revision. They go back to tentative, which
    # is what they were before expiring, so the 0021 check constraint still holds.
    op.execute("UPDATE venue_bookings SET status = 'tentative' WHERE status = 'expired'")
    op.drop_index("ix_venue_bookings_tentative_expires_at", table_name="venue_bookings")
