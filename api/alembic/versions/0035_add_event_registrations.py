"""Add attendee registration records and their append-only status history."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    status = sa.Enum(
        "pending",
        "waitlisted",
        "accepted",
        "withdrawn",
        "cancelled",
        name="registrationstatus",
        native_enum=False,
        length=20,
    )
    op.create_table(
        "event_registrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "event_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("event_requests.id"),
            nullable=False,
        ),
        sa.Column(
            "attendee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("status", status, nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submission_order", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_event_registrations_event_request_id",
        "event_registrations",
        ["event_request_id"],
    )
    op.create_index("ix_event_registrations_attendee_id", "event_registrations", ["attendee_id"])
    op.create_index(
        "uq_event_registration_submission_order",
        "event_registrations",
        ["event_request_id", "submission_order"],
        unique=True,
    )
    op.create_index(
        "uq_live_event_registration_attendee",
        "event_registrations",
        ["event_request_id", "attendee_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'waitlisted', 'accepted')"),
    )
    op.create_table(
        "event_registration_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "registration_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("event_registrations.id"),
            nullable=False,
        ),
        sa.Column("previous_status", status),
        sa.Column("status", status, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_event_registration_history_registration_id",
        "event_registration_history",
        ["registration_id"],
    )


def downgrade() -> None:
    op.drop_table("event_registration_history")
    op.drop_index("uq_live_event_registration_attendee", table_name="event_registrations")
    op.drop_table("event_registrations")
