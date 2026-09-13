"""add event request review decision

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "event_requests",
        sa.Column("decided_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "event_requests", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("event_requests", sa.Column("rejection_reason", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_event_requests_decided_by_id_users",
        "event_requests",
        "users",
        ["decided_by_id"],
        ["id"],
    )
    op.create_index("ix_event_requests_decided_by_id", "event_requests", ["decided_by_id"])


def downgrade() -> None:
    op.drop_index("ix_event_requests_decided_by_id", table_name="event_requests")
    op.drop_constraint(
        "fk_event_requests_decided_by_id_users", "event_requests", type_="foreignkey"
    )
    op.drop_column("event_requests", "rejection_reason")
    op.drop_column("event_requests", "decided_at")
    op.drop_column("event_requests", "decided_by_id")
