"""Record Safety Officer decisions on an event's plan (SCRUM-79).

One row per decision, never updated, so the history AC9 asks for is the table itself.
`plan_fingerprint` is what the decision was taken against (AC4, AC8); AC7 refuses a
decision once the plan no longer matches it.

No change to `event_requests`. A safety decision does not move the event's status: AC8
says approval "does not change the event to Confirmed", and AC5 says a rejection leaves
it in Approved/Planning, so there is nothing on the event to write.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "safety_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("plan_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("decided_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_request_id"], ["event_requests.id"]),
        sa.ForeignKeyConstraint(["decided_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        # AC4: a decision without a reason is not a review.
        sa.CheckConstraint("btrim(comment) <> ''", name="safety_reviews_comment_not_blank"),
    )
    op.create_index("ix_safety_reviews_event_request_id", "safety_reviews", ["event_request_id"])
    # AC5 and AC9 both read an event's newest decision, so the index matches that order.
    op.create_index(
        "ix_safety_reviews_event_decided_at",
        "safety_reviews",
        ["event_request_id", "decided_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_safety_reviews_event_decided_at", table_name="safety_reviews")
    op.drop_index("ix_safety_reviews_event_request_id", table_name="safety_reviews")
    op.drop_table("safety_reviews")
