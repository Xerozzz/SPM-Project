"""Venue Staff booking decision contracts (SCRUM-40, SCRUM-75)."""

import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field

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


class ConflictRead(BaseModel):
    """SCRUM-75 AC1: what the SCRUM-73 check says would block approving a request."""

    kind: Literal["booking", "unavailability"]
    id: uuid.UUID
    start_at: datetime
    end_at: datetime
    message: str

    @classmethod
    def from_error(cls, exc: ConflictingBookingError | VenueUnavailableError) -> Self:
        if isinstance(exc, ConflictingBookingError):
            booking = exc.booking
            return cls(
                kind="booking",
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
            conflict=_conflict_read(conflict),
        )


def _conflict_read(exc: BookingConflictError | None) -> ConflictRead | None:
    """Only the two named conflicts can come from the read-only SCRUM-73 check."""
    if isinstance(exc, (ConflictingBookingError, VenueUnavailableError)):
        return ConflictRead.from_error(exc)
    return None
