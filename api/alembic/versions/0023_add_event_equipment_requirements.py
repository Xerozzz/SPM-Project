"""Record an event's equipment requirements as rows (SCRUM-43).

ADR-0024 kept `event_requests.equipment_requirement` as a single string naming a catalogue
type, and said plainly that a quantity would need a new data model. This is that model.

The backfill is what makes AC1 true: every event that already names a type gets that type
as its first requirement, so the assigned Coordinator maintains what the organiser chose
rather than typing it again. Quantity one is the only honest reading of a field that never
held a number, and the requirement starts pending review (AC5) because nobody has assessed
it yet.

The organiser's column stays. Repointing the event-request form and venue suitability at
these rows means changing four merged stories and superseding part of ADR-0024, which is
its own piece of work; until then the column remains where the organiser's single choice
is captured and this table is what the Coordinator and Technical Support Staff work from.

Revision ID: 0023
Revises: 0022
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_equipment_requirements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "event_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("event_requests.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("equipment_type", sa.String(200), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("technical_requirements", sa.Text(), nullable=True),
        sa.Column("review_status", sa.String(30), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    # AC3: a requirement for none of something is not a requirement.
    op.create_check_constraint(
        "event_equipment_requirements_quantity_positive",
        "event_equipment_requirements",
        "quantity >= 1",
    )
    # AC4, and partial on purpose: a removed line keeps its row (AC7), so a plain unique
    # constraint would stop the same type ever being asked for again.
    op.create_index(
        "event_equipment_requirements_one_live_line_per_type",
        "event_equipment_requirements",
        ["event_request_id", "equipment_type"],
        unique=True,
        postgresql_where=sa.text("removed_at IS NULL"),
    )

    op.create_table(
        "equipment_requirement_changes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "requirement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("event_equipment_requirements.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "event_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("event_requests.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "changed_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("equipment_type", sa.String(200), nullable=False),
        sa.Column("old_quantity", sa.Integer(), nullable=True),
        sa.Column("new_quantity", sa.Integer(), nullable=True),
        sa.Column("old_technical_requirements", sa.Text(), nullable=True),
        sa.Column("new_technical_requirements", sa.Text(), nullable=True),
    )

    # AC1: what the organiser already chose becomes the first requirement, so the
    # Coordinator maintains it rather than entering it a second time. No audit row is
    # written for these: nobody performed this change, the schema did.
    #
    # Approved events only, matching where the application seeds at runtime. ADR-0033
    # rejects seeding earlier precisely because an organiser can still edit a draft or a
    # submitted request, which would leave the row and the string disagreeing while both
    # are live. Backfilling every status would have done that to every existing draft.
    #
    # The length guard exists because `create_draft` does not validate this column at all
    # (only `update_draft` and `submit` do), so a long pasted string could otherwise
    # overflow VARCHAR(200) and abort the upgrade half way through a deploy.
    op.execute(
        """
        INSERT INTO event_equipment_requirements (
            id, event_request_id, equipment_type, quantity,
            technical_requirements, review_status, removed_at, created_at, updated_at
        )
        SELECT gen_random_uuid(), e.id, btrim(e.equipment_requirement), 1,
               NULL, 'pending_review', NULL, now(), now()
        FROM event_requests AS e
        WHERE e.status = 'approved'
          AND e.equipment_requirement IS NOT NULL
          AND btrim(e.equipment_requirement) <> ''
          AND length(btrim(e.equipment_requirement)) <= 200
        """
    )


def downgrade() -> None:
    op.drop_table("equipment_requirement_changes")
    op.drop_index(
        "event_equipment_requirements_one_live_line_per_type",
        table_name="event_equipment_requirements",
    )
    op.drop_table("event_equipment_requirements")
