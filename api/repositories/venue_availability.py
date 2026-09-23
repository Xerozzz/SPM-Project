"""Availability queries for venue search (SCRUM-55). The only layer that reads the
booking and unavailability tables (ADR-0003)."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.venue_booking import VenueBooking
from models.venue_unavailability import VenueUnavailability


def venue_ids_with_confirmed_overlap(
    db: Session, start_at: datetime, end_at: datetime
) -> set[uuid.UUID]:
    """Venue ids holding a confirmed booking overlapping [start_at, end_at).

    Half-open, like domain.venue_search.intervals_overlap: a booking ending exactly at
    the requested start (or starting exactly at the requested end) does not overlap.
    Pending rows are ignored here, so they never block search (AC6).
    """
    statement = select(VenueBooking.venue_id).where(
        VenueBooking.status == "confirmed",
        VenueBooking.start_at < end_at,
        start_at < VenueBooking.end_at,
    )
    return set(db.scalars(statement))


def venue_ids_with_unavailability_overlap(
    db: Session, start_at: datetime, end_at: datetime
) -> set[uuid.UUID]:
    """Venue ids with an unavailability block overlapping [start_at, end_at) (AC5)."""
    statement = select(VenueUnavailability.venue_id).where(
        VenueUnavailability.start_at < end_at,
        start_at < VenueUnavailability.end_at,
    )
    return set(db.scalars(statement))
