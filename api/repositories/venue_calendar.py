"""Reads for the venue availability calendar (SCRUM-54)."""

import uuid
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import select
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
    """Bookings with one of `statuses` overlapping [start_at, end_at), with their venue.

    Half-open, like domain.venue_search.intervals_overlap.
    """
    statement = (
        select(VenueBooking, Venue)
        .join(Venue, Venue.id == VenueBooking.venue_id)
        .where(
            VenueBooking.status.in_(list(statuses)),
            VenueBooking.start_at < end_at,
            start_at < VenueBooking.end_at,
        )
    )
    if venue_id is not None:
        statement = statement.where(VenueBooking.venue_id == venue_id)
    return list(db.execute(statement).tuples())


def unavailabilities_in_range(
    db: Session, start_at: datetime, end_at: datetime, venue_id: uuid.UUID | None
) -> list[tuple[VenueUnavailability, Venue]]:
    """Unavailability blocks overlapping [start_at, end_at), with their venue."""
    statement = (
        select(VenueUnavailability, Venue)
        .join(Venue, Venue.id == VenueUnavailability.venue_id)
        .where(VenueUnavailability.starts_at < end_at, start_at < VenueUnavailability.ends_at)
    )
    if venue_id is not None:
        statement = statement.where(VenueUnavailability.venue_id == venue_id)
    return list(db.execute(statement).tuples())
