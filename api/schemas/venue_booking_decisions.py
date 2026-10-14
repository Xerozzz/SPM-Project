"""Venue Staff booking decision contracts (SCRUM-40, SCRUM-75)."""

import uuid
from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from domain.booking_conflict import (
    BookingConflictError,
    ConflictingBookingError,
    VenueUnavailableError,
)
from domain.venue_booking import BookingStatus
from domain.venue_booking_decision import MAX_REASON_LENGTH
from models.event_request import EventRequest
from models.venue import Venue
from models.venue_booking import VenueBooking


class VenueBookingReject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=MAX_REASON_LENGTH)


class VenueBookingHold(BaseModel):
    """SCRUM-83 AC1: when a tentative hold stops holding the venue."""

    model_config = ConfigDict(extra="forbid")

    # AwareDatetime: an expiry without a time zone is refused at the door (AGENTS.md 3).
    expires_at: AwareDatetime

    @field_validator("expires_at")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class ConflictRead(BaseModel):
    """SCRUM-75 AC1: what the SCRUM-73 check says would block approving a request.
    SCRUM-83: `hold` when the clash is a tentative hold rather than a confirmed booking."""

    kind: Literal["booking", "hold", "unavailability"]
    id: uuid.UUID
    start_at: datetime
    end_at: datetime
    message: str

    @classmethod
    def from_error(cls, exc: ConflictingBookingError | VenueUnavailableError) -> Self:
        if isinstance(exc, ConflictingBookingError):
            booking = exc.booking
            return cls(
                kind="hold" if booking.status is BookingStatus.TENTATIVE else "booking",
                id=booking.id,
                start_at=booking.start_at,
                end_at=booking.end_at,
                message=str(exc),
            )
        period = exc.period
        return cls(
            kind="unavailability",
            id=period.id,
            start_at=period.starts_at,
            end_at=period.ends_at,
            message=str(exc),
        )


class VenueBookingDecisionRead(BaseModel):
    """A booking request as Venue Staff see it: what, where, when, and the decision."""

    id: uuid.UUID
    status: BookingStatus
    venue_id: uuid.UUID
    venue_name: str
    venue_location: str
    event_request_id: uuid.UUID
    event_name: str | None
    start_at: datetime
    end_at: datetime
    expected_attendance: int | None
    venue_requirement: str | None
    accessibility_requirement: str | None
    equipment_requirement: str | None
    layout_requirement: str | None
    requested_by_id: uuid.UUID
    decided_by_id: uuid.UUID | None
    decided_at: datetime | None
    decision_reason: str | None
    # SCRUM-83: the hold, when Venue Staff placed one, and the event's assigned
    # Coordinator it is held for (AC1).
    expires_at: datetime | None = None
    held_by_id: uuid.UUID | None = None
    held_at: datetime | None = None
    coordinator_id: uuid.UUID | None = None
    conflict: ConflictRead | None = None

    @classmethod
    def from_context(
        cls,
        booking: VenueBooking,
        event: EventRequest,
        venue: Venue,
        conflict: BookingConflictError | None = None,
    ) -> Self:
        return cls(
            id=booking.id,
            status=booking.status,
            venue_id=venue.id,
            venue_name=venue.name,
            venue_location=venue.location,
            event_request_id=event.id,
            event_name=event.name,
            start_at=booking.start_at,
            end_at=booking.end_at,
            expected_attendance=event.expected_attendance,
            venue_requirement=event.venue_requirement,
            accessibility_requirement=event.accessibility_requirement,
            equipment_requirement=event.equipment_requirement,
            layout_requirement=event.layout_requirement,
            requested_by_id=booking.requested_by_id,
            decided_by_id=booking.decided_by_id,
            decided_at=booking.decided_at,
            decision_reason=booking.decision_reason,
            expires_at=booking.expires_at,
            held_by_id=booking.held_by_id,
            held_at=booking.held_at,
            coordinator_id=event.coordinator_id,
            conflict=_conflict_read(conflict),
        )


def _conflict_read(exc: BookingConflictError | None) -> ConflictRead | None:
    """Only the two named conflicts can come from the read-only SCRUM-73 check."""
    if isinstance(exc, (ConflictingBookingError, VenueUnavailableError)):
        return ConflictRead.from_error(exc)
    return None
