"""Store attendee-provided contact information with each registration submission."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "event_registrations",
        sa.Column("full_name", sa.String(length=200), nullable=True),
    )
    op.add_column("event_registrations", sa.Column("age", sa.Integer(), nullable=True))
    op.add_column(
        "event_registrations",
        sa.Column("phone_number", sa.String(length=50), nullable=True),
    )
    op.add_column("event_registrations", sa.Column("dietary_accessibility_notes", sa.Text()))
    op.execute("UPDATE event_registrations SET full_name = '', age = 0, phone_number = ''")
    op.alter_column("event_registrations", "full_name", nullable=False)
    op.alter_column("event_registrations", "age", nullable=False)
    op.alter_column("event_registrations", "phone_number", nullable=False)


def downgrade() -> None:
    op.drop_column("event_registrations", "dietary_accessibility_notes")
    op.drop_column("event_registrations", "phone_number")
    op.drop_column("event_registrations", "age")
    op.drop_column("event_registrations", "full_name")
