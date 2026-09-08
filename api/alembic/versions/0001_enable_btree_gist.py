"""enable the btree_gist extension

ADR-0002 prevents booking conflicts with a Postgres exclusion constraint of the form

    EXCLUDE USING gist (venue_id WITH =, period WITH &&) WHERE (status = 'CONFIRMED')

A GiST index natively understands the range half (`period WITH &&`) but not the scalar
equality half (`venue_id WITH =`). btree_gist adds the missing operator class. It has to
exist before any such constraint is created, so it gets its own first migration and this
one creates nothing else.

Revision ID: 0001
Revises:
Create Date: 2026-09-08
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
