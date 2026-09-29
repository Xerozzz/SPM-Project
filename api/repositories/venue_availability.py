"""Venue booking and unavailability persistence (SCRUM-55/SCRUM-38)."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.venue_booking import BookingStatus
from models.venue_booking import VenueBooking
from models.venue_unavailability import VenueUnavailability


def venue_ids_with_confirmed_overlap(
    db: Session, start_at: datetime, end_at: datetime
) -> set[uuid.UUID]:
    """Venue ids holding a confirmed booking overlapping [start_at, end_at).

    Half-open, like domain.venue_search.intervals_overlap: a booking ending exactly at
    the requested start (or starting exactly at the requested end) does not overlap.
    Pending rows are ignored here, so they never block search (AC6). The status
    comparison uses the same `BookingStatus` enum the domain rule takes, so the two
    cannot disagree on what "confirmed" means.
    """
    statement = select(VenueBooking.venue_id).where(
        VenueBooking.status == BookingStatus.CONFIRMED,
        VenueBooking.start_at < end_at,
        start_at < VenueBooking.end_at,
    )
    return set(db.scalars(statement))


def venue_ids_with_unavailability_overlap(
    db: Session, start_at: datetime, end_at: datetime
) -> set[uuid.UUID]:
    """Venue ids with an unavailability block overlapping [start_at, end_at) (AC5)."""
    statement = select(VenueUnavailability.venue_id).where(
        VenueUnavailability.starts_at < end_at,
        start_at < VenueUnavailability.ends_at,
    )
    return set(db.scalars(statement))


def pending_for_event(db: Session, event_request_id: uuid.UUID) -> VenueBooking | None:
    """Return the event's current pending request, if any."""
    statement = select(VenueBooking).where(
        VenueBooking.event_request_id == event_request_id,
        VenueBooking.status == BookingStatus.PENDING,
    )
    return db.scalars(statement).first()


def save_booking(db: Session, booking: VenueBooking) -> VenueBooking:
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking
