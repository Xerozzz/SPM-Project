"""Add setup and turnaround buffers to venues (SCRUM-82).

The minutes a venue needs to prepare before a booking and to reset after one. They live
on the venue rather than on the booking so a booking cannot override them (AC1).

Both default to zero and are NOT NULL, so every venue that already exists keeps behaving
exactly as it did before this revision (AC7). Applying the buffers to availability and
conflict detection is a separate revision, because that one has to change the overlap
constraint as well.

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default so the NOT NULL holds for rows that already exist; the model's own
    # default=0 covers rows inserted from the application.
    op.add_column(
        "venues",
        sa.Column("setup_minutes", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "venues",
        sa.Column("turnaround_minutes", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    # A negative buffer is refused by domain/venue.py; this is the backstop for anything
    # that reaches the table another way, in the spirit of ADR-0002.
    op.create_check_constraint(
        "venues_buffers_not_negative",
        "venues",
        "setup_minutes >= 0 AND turnaround_minutes >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("venues_buffers_not_negative", "venues", type_="check")
    op.drop_column("venues", "turnaround_minutes")
    op.drop_column("venues", "setup_minutes")
