"""Reads for the venue availability calendar (SCRUM-54, SCRUM-77, buffers SCRUM-82)."""

import uuid
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from domain.venue_booking import BookingStatus
from models.venue import Venue
from models.venue_booking import VenueBooking
from models.venue_unavailability import VenueUnavailability


def bookings_in_range(
    db: Session,
    start_at: datetime,
    end_at: datetime,
    statuses: Iterable[BookingStatus],
    venue_id: uuid.UUID | None,
) -> list[tuple[VenueBooking, Venue]]:
    """Bookings whose *effective* interval overlaps [start_at, end_at), with their venue.

    Half-open, like domain.venue_search.intervals_overlap.

    SCRUM-82 AC4: the booking is widened by its venue's buffers, so a booking whose setup
    or reset reaches into the window is included even when the event itself is outside it.
    Computed from the venue's current buffers rather than read from the booking's stored
    effective columns, so the calendar reflects a buffer change at once (ADR-0019).

    Only the booking side is widened here. `[start_at, end_at)` is whatever the caller is
    asking about: a viewing window for the calendar, or an already-widened period when
    `services.venue_calendar.availability` asks whether a venue is free.
    """
    statement = (
        select(VenueBooking, Venue)
        .join(Venue, Venue.id == VenueBooking.venue_id)
        .where(
            VenueBooking.status.in_(list(statuses)),
            VenueBooking.start_at - func.make_interval(0, 0, 0, 0, 0, Venue.setup_minutes) < end_at,
            start_at
            < VenueBooking.end_at + func.make_interval(0, 0, 0, 0, 0, Venue.turnaround_minutes),
        )
    )
    if venue_id is not None:
        statement = statement.where(VenueBooking.venue_id == venue_id)
    return list(db.execute(statement).tuples())


def unavailabilities_in_range(
    db: Session, start_at: datetime, end_at: datetime, venue_id: uuid.UUID | None
) -> list[tuple[VenueUnavailability, Venue]]:
    """Unavailability blocks overlapping [start_at, end_at), with their venue.

    Never widened: a closure already covers the whole period the venue is unusable, which
    is the asymmetry SCRUM-82 AC5 describes.
    """
    statement = (
        select(VenueUnavailability, Venue)
        .join(Venue, Venue.id == VenueUnavailability.venue_id)
        .where(VenueUnavailability.starts_at < end_at, start_at < VenueUnavailability.ends_at)
    )
    if venue_id is not None:
        statement = statement.where(VenueUnavailability.venue_id == venue_id)
    return list(db.execute(statement).tuples())


def booking_with_venue(db: Session, booking_id: uuid.UUID) -> tuple[VenueBooking, Venue] | None:
    statement = (
        select(VenueBooking, Venue)
        .join(Venue, Venue.id == VenueBooking.venue_id)
        .where(VenueBooking.id == booking_id)
    )
    return db.execute(statement).tuples().first()


def unavailability_with_venue(
    db: Session, unavailability_id: uuid.UUID
) -> tuple[VenueUnavailability, Venue] | None:
    statement = (
        select(VenueUnavailability, Venue)
        .join(Venue, Venue.id == VenueUnavailability.venue_id)
        .where(VenueUnavailability.id == unavailability_id)
    )
    return db.execute(statement).tuples().first()
