"""Mark a safety approval as no longer valid when its event goes back to planning."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("safety_reviews", sa.Column("invalidated_at", sa.DateTime(timezone=True)))
    op.add_column("safety_reviews", sa.Column("invalidation_cause", sa.String(32)))
    op.create_check_constraint(
        "safety_reviews_invalidation_complete",
        "safety_reviews",
        "(invalidated_at IS NULL) = (invalidation_cause IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("safety_reviews_invalidation_complete", "safety_reviews", type_="check")
    op.drop_column("safety_reviews", "invalidation_cause")
    op.drop_column("safety_reviews", "invalidated_at")
