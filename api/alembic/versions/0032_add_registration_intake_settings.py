"""Store operational registration intake controls separately from planning fields."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("event_requests", sa.Column("registration_opened_at", sa.DateTime(timezone=True)))
    op.add_column("event_requests", sa.Column("registration_closes_at", sa.DateTime(timezone=True)))
    op.add_column(
        "event_requests", sa.Column("registration_suspended_at", sa.DateTime(timezone=True))
    )


def downgrade() -> None:
    op.drop_column("event_requests", "registration_suspended_at")
    op.drop_column("event_requests", "registration_closes_at")
    op.drop_column("event_requests", "registration_opened_at")
