"""Venue booking and unavailability persistence (SCRUM-55/SCRUM-38/SCRUM-73/SCRUM-74)."""

import uuid
from datetime import datetime

from psycopg.errors import DeadlockDetected, ExclusionViolation
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from domain.booking_conflict import ConcurrentBookingConflictError
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


def get_booking(db: Session, booking_id: uuid.UUID) -> VenueBooking | None:
    """Return the booking with this id, or None."""
    return db.get(VenueBooking, booking_id)


def get_booking_for_update(db: Session, booking_id: uuid.UUID) -> VenueBooking | None:
    """Return the booking with this id, locked until the transaction ends (SCRUM-74).

    Locks the booking row only, never the venue (ADR-0002 rejected per-venue locking): two
    approvals of the *same* request serialise here, and the second sees the first's status.
    Overlapping *different* requests are kept apart by the exclusion constraint instead.
    Same pattern as repositories.event_requests.get_for_update.
    """
    return db.get(VenueBooking, booking_id, with_for_update=True, populate_existing=True)


def other_bookings_overlapping(db: Session, booking: VenueBooking) -> list[VenueBooking]:
    """Every other booking on the same venue overlapping `booking`'s period (SCRUM-73).

    Any status: whether a status blocks is the domain's decision (domain.booking_conflict),
    not the query's. The half-open bounds only narrow the rows loaded; the domain
    re-applies the same rule. The booking itself is excluded so re-checking a booking
    never reports it as conflicting with itself.
    """
    statement = (
        select(VenueBooking)
        .where(
            VenueBooking.venue_id == booking.venue_id,
            VenueBooking.id != booking.id,
            VenueBooking.start_at < booking.end_at,
            booking.start_at < VenueBooking.end_at,
        )
        .order_by(VenueBooking.start_at, VenueBooking.id)
    )
    return list(db.scalars(statement))


def unavailabilities_overlapping(db: Session, booking: VenueBooking) -> list[VenueUnavailability]:
    """Closures on `booking`'s venue overlapping its period, half-open (SCRUM-73 AC3/AC5)."""
    statement = (
        select(VenueUnavailability)
        .where(
            VenueUnavailability.venue_id == booking.venue_id,
            VenueUnavailability.starts_at < booking.end_at,
            booking.start_at < VenueUnavailability.ends_at,
        )
        .order_by(VenueUnavailability.starts_at, VenueUnavailability.id)
    )
    return list(db.scalars(statement))


def save_booking(db: Session, booking: VenueBooking) -> VenueBooking:
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


def save_confirmed_booking(db: Session, booking: VenueBooking) -> VenueBooking:
    """Commit a newly confirmed booking, translating the ADR-0002 exclusion constraint.

    If another overlapping booking on this venue was confirmed and committed after our
    friendly check ran, `venue_bookings_no_confirmed_overlap` refuses this commit. Only
    that violation becomes a domain conflict; any other integrity error is a bug and is
    re-raised unchanged.

    When two overlapping approvals commit at the same moment, each one's constraint
    check can wait on the other's row, and Postgres then aborts one of them with a
    deadlock instead of the exclusion violation. The outcome is the same, one of the
    two loses, so that deadlock is a conflict too.
    """
    try:
        return save_booking(db, booking)
    except IntegrityError as exc:
        db.rollback()
        if isinstance(exc.orig, ExclusionViolation):
            raise ConcurrentBookingConflictError from exc
        raise
    except OperationalError as exc:
        db.rollback()
        if isinstance(exc.orig, DeadlockDetected):
            raise ConcurrentBookingConflictError from exc
        raise
