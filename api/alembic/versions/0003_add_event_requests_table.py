"""add event_requests table

SCRUM-46 (F2/F6), shared with SCRUM-28 and SCRUM-29. Every content column is nullable
because drafts may be incomplete; completeness is enforced at submission by
domain/event_request.py, not by the schema. Status is a VARCHAR holding the lowercase
value of domain.event_status.EventStatus.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organiser_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "submitted", name="eventstatus", native_enum=False, length=30),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_attendance", sa.Integer(), nullable=True),
        sa.Column("venue_requirement", sa.Text(), nullable=True),
        sa.Column("accessibility_requirement", sa.Text(), nullable=True),
        sa.Column("equipment_requirement", sa.Text(), nullable=True),
        sa.Column("layout_requirement", sa.Text(), nullable=True),
        sa.Column("registration_requirement", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organiser_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_event_requests_organiser_id", "event_requests", ["organiser_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_event_requests_organiser_id", table_name="event_requests")
    op.drop_table("event_requests")
