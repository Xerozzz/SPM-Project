"""add organisation membership for draft visibility

SCRUM-29: draft visibility is scoped to the client organisation. Users belong to an
organisation; shared draft visibility is derived from the creating organiser.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-14
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFAULT_ORG_ID = uuid.UUID("00000000-0000-4000-8000-000000000010")


def upgrade() -> None:
    op.create_table(
        "organisations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    organisations = sa.table(
        "organisations",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String(length=200)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        organisations,
        [
            {
                "id": _DEFAULT_ORG_ID,
                "name": "Default Client Organisation",
                "created_at": datetime.now(UTC),
            }
        ],
    )

    op.add_column(
        "users",
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    users = sa.table("users", sa.column("organisation_id", postgresql.UUID(as_uuid=True)))
    op.execute(users.update().values(organisation_id=_DEFAULT_ORG_ID))

    op.alter_column("users", "organisation_id", nullable=False)
    op.create_index("ix_users_organisation_id", "users", ["organisation_id"], unique=False)
    op.create_foreign_key(
        "fk_users_organisation_id_organisations",
        "users",
        "organisations",
        ["organisation_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_organisation_id_organisations", "users", type_="foreignkey")
    op.drop_index("ix_users_organisation_id", table_name="users")
    op.drop_column("users", "organisation_id")
    op.drop_table("organisations")
