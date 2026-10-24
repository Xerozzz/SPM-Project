"""Record event completion and its closure notes (SCRUM-86).

`completed_by_id` and `completed_at` say who completed the event and when. Closure notes
are versioned rows, so a correction adds a version and earlier values stay (ADR-0059).

Revision ID: 0041
Revises: 0040
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "event_requests", sa.Column("completed_by_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "event_requests", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        "event_requests_completed_by_id_fkey",
        "event_requests",
        "users",
        ["completed_by_id"],
        ["id"],
    )
    op.create_table(
        "event_closure_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "event_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("event_requests.id"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("actual_attendance", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "recorded_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_request_id", "version", name="event_closure_notes_one_version"),
        sa.CheckConstraint(
            "actual_attendance IS NULL OR actual_attendance >= 0",
            name="event_closure_notes_attendance_not_negative",
        ),
        sa.CheckConstraint("version >= 1", name="event_closure_notes_version_positive"),
    )
    op.create_index(
        "ix_event_closure_notes_event_request_id", "event_closure_notes", ["event_request_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_event_closure_notes_event_request_id", table_name="event_closure_notes")
    op.drop_table("event_closure_notes")
    op.drop_constraint("event_requests_completed_by_id_fkey", "event_requests", type_="foreignkey")
    op.drop_column("event_requests", "completed_at")
    op.drop_column("event_requests", "completed_by_id")
