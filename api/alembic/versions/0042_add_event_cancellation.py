"""Cancel an event and release its arrangements (SCRUM-115).

`cancelled_by_id`, `cancelled_at` and `cancellation_reason` say who cancelled the event,
when and why. An Organiser's cancellation requests are rows of their own, so each request
and its outcome stay, with at most one pending per event. `released_by_id` records who
released an equipment reservation, beside the existing `released_at` (ADR-0061).

Revision ID: 0042
Revises: 0041
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "event_requests", sa.Column("cancelled_by_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "event_requests", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("event_requests", sa.Column("cancellation_reason", sa.Text(), nullable=True))
    op.create_foreign_key(
        "event_requests_cancelled_by_id_fkey",
        "event_requests",
        "users",
        ["cancelled_by_id"],
        ["id"],
    )
    op.add_column(
        "equipment_reservations",
        sa.Column("released_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "equipment_reservations_released_by_id_fkey",
        "equipment_reservations",
        "users",
        ["released_by_id"],
        ["id"],
    )
    op.create_table(
        "event_cancellation_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "event_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("event_requests.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "requested_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "decided_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_event_cancellation_requests_event_request_id",
        "event_cancellation_requests",
        ["event_request_id"],
    )
    op.create_index(
        "uq_event_cancellation_requests_one_pending",
        "event_cancellation_requests",
        ["event_request_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_event_cancellation_requests_one_pending", table_name="event_cancellation_requests"
    )
    op.drop_index(
        "ix_event_cancellation_requests_event_request_id", table_name="event_cancellation_requests"
    )
    op.drop_table("event_cancellation_requests")
    op.drop_constraint(
        "equipment_reservations_released_by_id_fkey", "equipment_reservations", type_="foreignkey"
    )
    op.drop_column("equipment_reservations", "released_by_id")
    op.drop_constraint("event_requests_cancelled_by_id_fkey", "event_requests", type_="foreignkey")
    op.drop_column("event_requests", "cancellation_reason")
    op.drop_column("event_requests", "cancelled_at")
    op.drop_column("event_requests", "cancelled_by_id")
