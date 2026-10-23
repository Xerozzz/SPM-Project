"""One attendee's registration lifecycle for an event (SCRUM-42)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from domain.registration import RegistrationStatus


def _now() -> datetime:
    return datetime.now(UTC)


class EventRegistration(Base):
    """Current registration state; later stories append history instead of replacing it."""

    __tablename__ = "event_registrations"
    __table_args__ = (
        Index(
            "uq_live_event_registration_attendee",
            "event_request_id",
            "attendee_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'waitlisted', 'accepted')"),
        ),
        Index(
            "uq_event_registration_submission_order",
            "event_request_id",
            "submission_order",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event_requests.id"), nullable=False, index=True
    )
    attendee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    status: Mapped[RegistrationStatus] = mapped_column(
        Enum(
            RegistrationStatus,
            native_enum=False,
            length=20,
            values_callable=lambda members: [member.value for member in members],
        ),
        nullable=False,
        default=RegistrationStatus.PENDING,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    submission_order: Mapped[int] = mapped_column(Integer, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    phone_number: Mapped[str] = mapped_column(String(50), nullable=False)
    dietary_accessibility_notes: Mapped[str | None] = mapped_column(Text)


class EventRegistrationHistory(Base):
    """Immutable source action recording one registration status transition."""

    __tablename__ = "event_registration_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    registration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event_registrations.id"), nullable=False, index=True
    )
    previous_status: Mapped[RegistrationStatus | None] = mapped_column(
        Enum(
            RegistrationStatus,
            native_enum=False,
            length=20,
            values_callable=lambda members: [member.value for member in members],
        )
    )
    status: Mapped[RegistrationStatus] = mapped_column(
        Enum(
            RegistrationStatus,
            native_enum=False,
            length=20,
            values_callable=lambda members: [member.value for member in members],
        ),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
