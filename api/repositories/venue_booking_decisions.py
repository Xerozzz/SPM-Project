"""Reads for Venue Staff reviewing booking requests (SCRUM-40). Locking and saving a
booking reuse repositories.venue_availability, as approve does (SCRUM-74)."""

import uuid

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from models.event_request import EventRequest
from models.venue import Venue
from models.venue_booking import VenueBooking

BookingContext = tuple[VenueBooking, EventRequest, Venue]


def _with_context() -> Select[tuple[VenueBooking, EventRequest, Venue]]:
    """Each booking with the event and venue Venue Staff need to judge it (AC1)."""
    return (
        select(VenueBooking, EventRequest, Venue)
        .join(EventRequest, EventRequest.id == VenueBooking.event_request_id)
        .join(Venue, Venue.id == VenueBooking.venue_id)
    )


def list_with_context(db: Session) -> list[BookingContext]:
    """Every booking request, newest first."""
    statement = _with_context().order_by(VenueBooking.created_at.desc())
    return list(db.execute(statement).tuples())


def get_with_context(db: Session, booking_id: uuid.UUID) -> BookingContext | None:
    statement = _with_context().where(VenueBooking.id == booking_id)
    return db.execute(statement).tuples().first()
