"""A record of someone adding, changing or removing an equipment requirement (SCRUM-43 AC8).

Immutable once written, for the reason ADR-0027 gives about the venue buffer audit: an
audit row answers "what did this person do", and that answer must not move when the thing
they did it to moves afterwards.

Old and new values are stored side by side so one row stands on its own. An `added` row
has no old values and a `removed` row has no new ones, which is why both sides are
nullable rather than the row being three different shapes.
"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


def _now() -> datetime:
    return datetime.now(UTC)


class RequirementAction(StrEnum):
    """What was done to the requirement. AC8 asks for add, update and removal."""

    ADDED = "added"
    UPDATED = "updated"
    REMOVED = "removed"


class EquipmentRequirementChange(Base):
    """One change to one equipment requirement, with who, when, and both sides of it."""

    __tablename__ = "equipment_requirement_changes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("event_equipment_requirements.id"),
        nullable=False,
        index=True,
    )
    # Kept alongside the requirement id so the history of an event reads without joining
    # through a requirement that may since have been removed.
    event_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event_requests.id"), nullable=False, index=True
    )
    changed_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    action: Mapped[RequirementAction] = mapped_column(String(20), nullable=False)
    equipment_type: Mapped[str] = mapped_column(String(200), nullable=False)
    old_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    old_technical_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_technical_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
