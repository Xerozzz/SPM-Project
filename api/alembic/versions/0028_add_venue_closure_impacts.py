"""Record which arrangements a saved venue closure affected (SCRUM-81).

Closures may now be recorded over confirmed bookings and live holds. Each save that hits
at least one keeps a snapshot of what it affected, for history and for replacement
(ADR-0044). No existing rows change.

Revision ID: 0028
Revises: 0027
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "venue_closure_impacts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("unavailability_id", sa.UUID(), nullable=False),
        sa.Column("venue_id", sa.UUID(), nullable=False),
        sa.Column("recorded_by_id", sa.UUID(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("affected_booking_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.ForeignKeyConstraint(["recorded_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_venue_closure_impacts_unavailability_id",
        "venue_closure_impacts",
        ["unavailability_id"],
    )
    op.create_index("ix_venue_closure_impacts_venue_id", "venue_closure_impacts", ["venue_id"])


def downgrade() -> None:
    op.drop_index("ix_venue_closure_impacts_venue_id", table_name="venue_closure_impacts")
    op.drop_index("ix_venue_closure_impacts_unavailability_id", table_name="venue_closure_impacts")
    op.drop_table("venue_closure_impacts")
