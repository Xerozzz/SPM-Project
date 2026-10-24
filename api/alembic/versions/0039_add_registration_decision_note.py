"""Retain optional notes on manual registration status decisions.

Revision ID: 0039
Revises: 0038
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("event_registration_history", sa.Column("note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("event_registration_history", "note")
