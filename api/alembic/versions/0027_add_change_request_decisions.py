"""Record the decision on a significant-change request (SCRUM-47).

The assigned Coordinator approves or rejects a pending change request with a note. The
request keeps who decided and when, and each item keeps whether the approval applied it
or left it for replanning (ADR-0043). All new columns are nullable, so existing pending
requests need no backfill.

Revision ID: 0027
Revises: 0026
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("event_change_requests", sa.Column("decided_by_id", sa.UUID(), nullable=True))
    op.add_column(
        "event_change_requests",
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("event_change_requests", sa.Column("decision_note", sa.Text(), nullable=True))
    op.create_foreign_key(
        "event_change_requests_decided_by_id_fkey",
        "event_change_requests",
        "users",
        ["decided_by_id"],
        ["id"],
    )
    op.add_column("event_change_items", sa.Column("outcome", sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column("event_change_items", "outcome")
    op.drop_constraint(
        "event_change_requests_decided_by_id_fkey", "event_change_requests", type_="foreignkey"
    )
    op.drop_column("event_change_requests", "decision_note")
    op.drop_column("event_change_requests", "decided_at")
    op.drop_column("event_change_requests", "decided_by_id")
