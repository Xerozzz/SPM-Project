"""Venue Staff booking decision contracts (SCRUM-40)."""

import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from domain.venue_booking import BookingStatus
from domain.venue_booking_decision import MAX_REASON_LENGTH
from models.event_request import EventRequest
from models.venue import Venue
from models.venue_booking import VenueBooking


class VenueBookingReject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=MAX_REASON_LENGTH)


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

    @classmethod
    def from_context(cls, booking: VenueBooking, event: EventRequest, venue: Venue) -> Self:
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
        )
