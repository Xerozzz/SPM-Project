"""Add significant-change requests and their items (SCRUM-37).

An Organiser proposes changes to a submitted, approved or confirmed event instead of
editing it. A request keeps the reason, the requester and the event version it was made
against; each item keeps one changed value next to the value it would replace. The
unique (event, submission key) pair makes a retried submit find its first request
rather than create a second (ADR-0041).

Revision ID: 0026
Revises: 0025
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_change_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_request_id", sa.UUID(), nullable=False),
        sa.Column("requested_by_id", sa.UUID(), nullable=False),
        sa.Column("submission_key", sa.UUID(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("event_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_request_id"], ["event_requests.id"]),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_request_id", "submission_key", name="event_change_requests_one_per_submission"
        ),
    )
    op.create_index(
        op.f("ix_event_change_requests_event_request_id"),
        "event_change_requests",
        ["event_request_id"],
    )
    op.create_table(
        "event_change_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("change_request_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("target", sa.String(length=20), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=True),
        sa.Column("field", sa.String(length=60), nullable=False),
        sa.Column("current_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("proposed_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["change_request_id"], ["event_change_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_event_change_items_change_request_id"),
        "event_change_items",
        ["change_request_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_event_change_items_change_request_id"), table_name="event_change_items")
    op.drop_table("event_change_items")
    op.drop_index(
        op.f("ix_event_change_requests_event_request_id"), table_name="event_change_requests"
    )
    op.drop_table("event_change_requests")
