"""API contracts for confirming an event (SCRUM-80)."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from domain.event_confirmation import ConfirmationProblems
from models.event_request import EventRequest
from models.venue_booking import VenueBooking


class ConfirmedBookingRead(BaseModel):
    """AC4: one arrangement that is now a real booking rather than a hold."""

    booking_id: uuid.UUID
    venue_id: uuid.UUID
    session_label: str
    start_at: datetime
    end_at: datetime

    @classmethod
    def of(cls, booking: VenueBooking) -> "ConfirmedBookingRead":
        return cls(
            booking_id=booking.id,
            venue_id=booking.venue_id,
            session_label=booking.session_label,
            start_at=booking.start_at,
            end_at=booking.end_at,
        )


class ConfirmationReadinessRead(BaseModel):
    """AC2, AC3 and AC10: whether this event may be confirmed, and what is missing.

    The two lists are kept apart because they are owed by different people: the
    arrangement reasons are work for Venue Staff, Technical Support and the Coordinator
    themselves, while the safety reasons are the Officer's to clear. A screen that
    flattened them would tell the Coordinator to go and fix something that is not theirs.
    """

    event_request_id: uuid.UUID
    may_confirm: bool
    #: SCRUM-79's `ReviewBlocker` vocabulary, reused rather than restated.
    arrangement_blockers: list[str]
    #: SCRUM-80's own `ConfirmationBlocker` vocabulary.
    safety_blockers: list[str]

    @classmethod
    def of(cls, event: EventRequest, found: ConfirmationProblems) -> "ConfirmationReadinessRead":
        return cls(
            event_request_id=event.id,
            may_confirm=not found.blocked,
            arrangement_blockers=[reason.value for reason in found.arrangement],
            safety_blockers=[reason.value for reason in found.safety],
        )


class ConfirmationRead(BaseModel):
    """AC4 and AC6: what confirmation did, and the audit it recorded."""

    event_request_id: uuid.UUID
    status: str
    confirmed_by_id: uuid.UUID | None
    confirmed_at: datetime | None
    #: The holds that became bookings, so the Coordinator sees what was committed.
    confirmed_bookings: list[ConfirmedBookingRead]

    @classmethod
    def of(cls, event: EventRequest, bookings: list[VenueBooking]) -> "ConfirmationRead":
        return cls(
            event_request_id=event.id,
            status=event.status.value,
            confirmed_by_id=event.confirmed_by_id,
            confirmed_at=event.confirmed_at,
            confirmed_bookings=[ConfirmedBookingRead.of(booking) for booking in bookings],
        )
