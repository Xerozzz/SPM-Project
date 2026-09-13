"""add event request clarification details

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "event_requests",
        sa.Column("clarification_requested_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "event_requests",
        sa.Column("clarification_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("event_requests", sa.Column("clarification_request", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_event_requests_clarification_requested_by_id_users",
        "event_requests",
        "users",
        ["clarification_requested_by_id"],
        ["id"],
    )
    op.create_index(
        "ix_event_requests_clarification_requested_by_id",
        "event_requests",
        ["clarification_requested_by_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_event_requests_clarification_requested_by_id", table_name="event_requests")
    op.drop_constraint(
        "fk_event_requests_clarification_requested_by_id_users",
        "event_requests",
        type_="foreignkey",
    )
    op.drop_column("event_requests", "clarification_request")
    op.drop_column("event_requests", "clarification_requested_at")
    op.drop_column("event_requests", "clarification_requested_by_id")
