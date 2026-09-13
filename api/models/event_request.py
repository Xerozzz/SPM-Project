"""An organiser's request for an event. Shared by SCRUM-28 (create), SCRUM-29 (draft
save/resume), SCRUM-46 (submit) and the review stories, so it carries every field the
ticket names from day one.

Content columns are nullable on purpose: a draft may be saved half-finished (SCRUM-29).
Whether it is complete enough to submit is a domain rule, not a database constraint —
see domain/event_request.py.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from domain.event_status import EventStatus


def _now() -> datetime:
    return datetime.now(UTC)


class EventRequest(Base):
    """One event request, owned by the organiser who created it."""

    __tablename__ = "event_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organiser_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    # Stored as the enum's lowercase value in a plain VARCHAR (native_enum=False), so
    # adding a status later is a code change, not a Postgres type migration.
    status: Mapped[EventStatus] = mapped_column(
        Enum(
            EventStatus,
            native_enum=False,
            length=30,
            values_callable=lambda members: [m.value for m in members],
        ),
        nullable=False,
        default=EventStatus.DRAFT,
    )

    name: Mapped[str | None] = mapped_column(Text)
    purpose: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expected_attendance: Mapped[int | None] = mapped_column(Integer)
    venue_requirement: Mapped[str | None] = mapped_column(Text)
    accessibility_requirement: Mapped[str | None] = mapped_column(Text)
    equipment_requirement: Mapped[str | None] = mapped_column(Text)
    layout_requirement: Mapped[str | None] = mapped_column(Text)
    registration_requirement: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # SCRUM-34: the Event Coordinator auto-assigned on first submission, and when.
    coordinator_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    clarification_requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    clarification_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    clarification_request: Mapped[str | None] = mapped_column(Text)
