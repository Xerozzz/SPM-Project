"""add venue booking decision

SCRUM-40 records who decided a venue booking request, when, and why. The columns stay
empty while the request is pending. They mirror the event request review decision
added in 0007 (ADR-0011), so both decisions are audited the same way. See ADR-0018.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "venue_bookings",
        sa.Column("decided_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "venue_bookings", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("venue_bookings", sa.Column("decision_reason", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_venue_bookings_decided_by_id_users",
        "venue_bookings",
        "users",
        ["decided_by_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_venue_bookings_decided_by_id_users", "venue_bookings", type_="foreignkey"
    )
    op.drop_column("venue_bookings", "decision_reason")
    op.drop_column("venue_bookings", "decided_at")
    op.drop_column("venue_bookings", "decided_by_id")
