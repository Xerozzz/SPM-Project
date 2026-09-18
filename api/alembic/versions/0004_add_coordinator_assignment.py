"""add coordinator assignment columns

SCRUM-34: on first submission, an event request is auto-assigned exactly one active
Event Coordinator. `users.is_active` marks who is eligible; `event_requests` records
the assignment once made via `coordinator_id` + `assigned_at`.

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
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "event_requests",
        sa.Column("coordinator_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "event_requests",
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_event_requests_coordinator_id_users",
        "event_requests",
        "users",
        ["coordinator_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_event_requests_coordinator_id_users", "event_requests", type_="foreignkey"
    )
    op.drop_column("event_requests", "assigned_at")
    op.drop_column("event_requests", "coordinator_id")
    op.drop_column("users", "is_active")
