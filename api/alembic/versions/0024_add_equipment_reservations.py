"""Reserve equipment for an event (SCRUM-53). ADR-0038.

One row is one act of reserving: a quantity of one catalogue type, for one requirement,
over the event's window as it was at that moment. Reserving twice for the same
requirement (a partial reservation topped up later) adds a second row rather than editing
the first, so each row says who committed how many and when.

The window is copied rather than joined, so the reservation keeps meaning what it meant
when it was made even if the event moves. Releasing or flagging it when the event changes
is Event Change Management's work; `released_at` and `flagged_at` exist now so that
story fills columns in rather than altering this table.

Revision ID: 0024
Revises: 0023
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "equipment_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "requirement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("event_equipment_requirements.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "event_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("event_requests.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("equipment_type", sa.String(200), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("flagged_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Reserving none of something is not a reservation.
    op.create_check_constraint(
        "equipment_reservations_quantity_positive", "equipment_reservations", "quantity >= 1"
    )
    # A window that ends before it starts would overlap nothing and hide a bug.
    op.create_check_constraint(
        "equipment_reservations_window_ordered", "equipment_reservations", "starts_at < ends_at"
    )
    # Every availability check sums live reservations of one type, so index exactly those.
    op.create_index(
        "ix_equipment_reservations_live_type",
        "equipment_reservations",
        ["equipment_type"],
        postgresql_where=sa.text("released_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_equipment_reservations_live_type", table_name="equipment_reservations")
    op.drop_table("equipment_reservations")
