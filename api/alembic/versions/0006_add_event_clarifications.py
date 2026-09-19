"""add event clarification messages

SCRUM-30 retains coordinator clarification requests and organiser responses as one
chronological message history linked to the event request.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_clarifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        # "request" (coordinator asks) or "response" (organiser answers). A plain
        # VARCHAR holding domain.event_clarification.ClarificationKind, like status.
        sa.Column(
            "kind",
            sa.Enum("request", "response", name="clarificationkind", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["event_request_id"], ["event_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_event_clarifications_event_request_id",
        "event_clarifications",
        ["event_request_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_event_clarifications_event_request_id", table_name="event_clarifications")
    op.drop_table("event_clarifications")
