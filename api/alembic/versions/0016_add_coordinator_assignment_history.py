"""add coordinator assignment history

SCRUM-97 retains every coordinator ownership change as an append-only audit trail:
event request, previous coordinator (null for the first assignment), new
coordinator, acting Lead, and a timezone-aware UTC timestamp. Current ownership
stays on `event_requests` for authorisation; this table never feeds it. See
ADR-0021.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_coordinator_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("previous_coordinator_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("new_coordinator_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("acted_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["acted_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["event_request_id"], ["event_requests.id"]),
        sa.ForeignKeyConstraint(["new_coordinator_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["previous_coordinator_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_event_coordinator_assignments_event_request_id",
        "event_coordinator_assignments",
        ["event_request_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_event_coordinator_assignments_event_request_id",
        table_name="event_coordinator_assignments",
    )
    op.drop_table("event_coordinator_assignments")
