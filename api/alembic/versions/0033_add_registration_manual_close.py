"""Record a manual registration closure independently of a deadline or suspension."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "event_requests",
        sa.Column("registration_closed_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_column("event_requests", "registration_closed_at")
