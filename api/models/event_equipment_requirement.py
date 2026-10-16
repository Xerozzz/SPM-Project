"""One piece of equipment an event needs, and how many (SCRUM-43).

Records rather than a sentence. `event_requests.equipment_requirement` holds the single
type the organiser picked when raising the request (ADR-0024); this table is what the
assigned Coordinator maintains from then on, seeded from that value so nothing is
re-entered (AC1), and what Technical Support Staff assess (SCRUM-44).

Removal is soft. AC7 asks for removed requirements to stay identifiable in the event's
history while no longer counting toward availability, which a deleted row cannot do.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from domain.equipment_requirement import RequirementReview


def _now() -> datetime:
    return datetime.now(UTC)


class EventEquipmentRequirement(Base):
    """A quantity of one catalogue equipment type, required by one event."""

    __tablename__ = "event_equipment_requirements"
    __table_args__ = (
        # AC4: one *live* line per type per event, as a partial unique index rather than a
        # plain unique constraint. A removed line keeps its row (AC7), so a plain
        # constraint would stop the same type ever being asked for again, which is the
        # opposite of what soft removal is for.
        Index(
            "event_equipment_requirements_one_live_line_per_type",
            "event_request_id",
            "equipment_type",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event_requests.id"), nullable=False, index=True
    )
    # The catalogue's type, not an id: ADR-0024 decided an event asks for a kind of thing,
    # not a particular item in a particular place.
    equipment_type: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    technical_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    # AC5: set back to pending whenever the line changes, because whatever Technical
    # Support Staff last said is about a requirement that no longer exists in that form.
    review_status: Mapped[RequirementReview] = mapped_column(
        String(30), nullable=False, default=RequirementReview.PENDING_REVIEW
    )
    # AC7: soft removal. Null means the requirement is live.
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )
