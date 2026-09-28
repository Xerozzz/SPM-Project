"""associate venue booking requests with their event and coordinator

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("venue_bookings") as batch:
        batch.add_column(sa.Column("event_request_id", postgresql.UUID(as_uuid=True)))
        batch.add_column(sa.Column("requested_by_id", postgresql.UUID(as_uuid=True)))
        batch.create_foreign_key("fk_booking_event", "event_requests", ["event_request_id"], ["id"])
        batch.create_foreign_key("fk_booking_requester", "users", ["requested_by_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("venue_bookings") as batch:
        batch.drop_constraint("fk_booking_requester", type_="foreignkey")
        batch.drop_constraint("fk_booking_event", type_="foreignkey")
        batch.drop_column("requested_by_id")
        batch.drop_column("event_request_id")
