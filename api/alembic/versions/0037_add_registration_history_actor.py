"""Record the actor that performed each registration status transition."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "event_registration_history",
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_event_registration_history_actor_id_users",
        "event_registration_history",
        "users",
        ["actor_id"],
        ["id"],
    )
    op.execute(
        """
        UPDATE event_registration_history AS history
        SET actor_id = registration.attendee_id
        FROM event_registrations AS registration
        WHERE history.registration_id = registration.id
        """
    )
    op.alter_column("event_registration_history", "actor_id", nullable=False)
    op.create_index(
        "ix_event_registration_history_actor_id", "event_registration_history", ["actor_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_event_registration_history_actor_id", table_name="event_registration_history")
    op.drop_constraint(
        "fk_event_registration_history_actor_id_users",
        "event_registration_history",
        type_="foreignkey",
    )
    op.drop_column("event_registration_history", "actor_id")
