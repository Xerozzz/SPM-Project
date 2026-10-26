"""Reminders the Coordinator asked for before their event (SCRUM-85).

One row per lead time per event. The row carries both the schedule and whether its
occurrence has been processed, so "at most one reminder per occurrence" (AC6) is a flag
on a locked row rather than a ledger to reconcile.

The due time is deliberately not stored: it is the event's start less the lead time, so
moving the event moves every future occurrence with it while anything already processed
stays processed (AC8).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_reminders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lead_minutes", sa.Integer(), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("lead_minutes > 0", name="event_reminders_lead_minutes_positive"),
        sa.ForeignKeyConstraint(["event_request_id"], ["event_requests.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_request_id", "lead_minutes", name="uq_event_reminder_lead"),
    )
    op.create_index("ix_event_reminders_event_request_id", "event_reminders", ["event_request_id"])
    op.create_index(
        "ix_event_reminders_unprocessed", "event_reminders", ["processed_at", "event_request_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_event_reminders_unprocessed", table_name="event_reminders")
    op.drop_index("ix_event_reminders_event_request_id", table_name="event_reminders")
    op.drop_table("event_reminders")
