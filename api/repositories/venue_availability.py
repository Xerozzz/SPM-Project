"""Venue booking and unavailability persistence (SCRUM-55/38/73/74, buffers SCRUM-82)."""

import uuid
from datetime import datetime, timedelta

from psycopg.errors import DeadlockDetected, ExclusionViolation
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from domain.booking_conflict import ConcurrentBookingConflictError
from domain.venue_booking import BookingStatus
from domain.venue_search import BLOCKING_STATUSES
from models.venue import Venue
from models.venue_booking import VenueBooking
from models.venue_unavailability import VenueUnavailability


# SCRUM-82: the venue's buffers as SQL intervals, so a period can be widened inside the
# query. `make_interval(mins => n)` is read positionally here because SQLAlchemy's `func`
# emits positional arguments: years, months, weeks, days, hours, minutes, seconds.
def _setup() -> ColumnElement[timedelta]:
    return func.make_interval(0, 0, 0, 0, 0, Venue.setup_minutes)


def _turnaround() -> ColumnElement[timedelta]:
    return func.make_interval(0, 0, 0, 0, 0, Venue.turnaround_minutes)


def _combined_buffer_gap() -> ColumnElement[timedelta]:
    """The clear time two bookings at one venue need between them (AC6).

    Setup plus turnaround, added once. Widening both bookings is the same condition as
    requiring this gap between their event periods, which keeps these queries on raw
    columns; `test_widening_both_sides_equals_one_combined_gap` proves the equivalence.
    """
    return func.make_interval(0, 0, 0, 0, 0, Venue.setup_minutes + Venue.turnaround_minutes)


def venue_ids_with_confirmed_overlap(
    db: Session, start_at: datetime, end_at: datetime
) -> set[uuid.UUID]:
    """Venue ids holding a confirmed booking or tentative hold overlapping the period.

    Half-open, like domain.venue_search.intervals_overlap: a booking ending exactly at
    the requested start (or starting exactly at the requested end) does not overlap.
    Pending rows are ignored here, so they never block search (AC6). The statuses are
    the domain's BLOCKING_STATUSES, so this query and booking_blocks_availability
    cannot disagree on what blocks (SCRUM-83 AC3).
    """
    gap = _combined_buffer_gap()
    statement = (
        select(VenueBooking.venue_id)
        .join(Venue, Venue.id == VenueBooking.venue_id)
        .where(
            VenueBooking.status.in_(BLOCKING_STATUSES),
            VenueBooking.start_at < end_at + gap,
            start_at < VenueBooking.end_at + gap,
        )
    )
    return set(db.scalars(statement))


def venue_ids_with_unavailability_overlap(
    db: Session, start_at: datetime, end_at: datetime
) -> set[uuid.UUID]:
    """Venue ids with an unavailability block overlapping [start_at, end_at) (AC5).

    SCRUM-82: the requested period is widened by the venue's buffers because a booking
    made for it would need them; the closure is not, for the reason in
    `unavailabilities_overlapping`.
    """
    statement = (
        select(VenueUnavailability.venue_id)
        .join(Venue, Venue.id == VenueUnavailability.venue_id)
        .where(
            VenueUnavailability.starts_at < end_at + _turnaround(),
            start_at - _setup() < VenueUnavailability.ends_at,
        )
    )
    return set(db.scalars(statement))


def list_bookings_for_event(db: Session, event_request_id: uuid.UUID) -> list[VenueBooking]:
    """Return every booking request retained for one event, oldest first."""
    statement = (
        select(VenueBooking)
        .where(VenueBooking.event_request_id == event_request_id)
        .order_by(VenueBooking.created_at, VenueBooking.id)
    )
    return list(db.scalars(statement))


def confirmed_bookings_from(db: Session, venue_id: uuid.UUID, now: datetime) -> list[VenueBooking]:
    """SCRUM-89 AC1: confirmed bookings at this venue still occupying it at or after `now`.

    The cut is the *effective* end, the event's end plus the venue's turnaround, not the
    event's own end. That matters because these rows play two parts: they are the bookings
    being assessed, and they are what each other booking is assessed against. An event
    that finished ten minutes ago still holds the venue while its turnaround runs, so
    dropping it would hide a real clash with the booking that follows it.

    Cutting on the event's end instead was a bug: with an hour of turnaround, a booking
    that ended at 10:00 still occupies the venue until 11:00, and a 10:30 booking that
    genuinely could not be approved was reported as fine.

    Anything whose effective interval has passed is left out, because nothing can be done
    about it and it can no longer be in anyone's way.

    Ordered so the review reports the same bookings in the same order every time.
    """
    statement = (
        select(VenueBooking)
        .join(Venue, Venue.id == VenueBooking.venue_id)
        .where(
            VenueBooking.venue_id == venue_id,
            VenueBooking.status == BookingStatus.CONFIRMED,
            VenueBooking.end_at + _turnaround() > now,
        )
        .order_by(VenueBooking.start_at, VenueBooking.id)
    )
    return list(db.scalars(statement))


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

    SCRUM-82: widened by the venue's buffers on both sides, because both bookings need
    their own setup and reset. Rather than widen each side, this adds the combined gap
    once to the raw comparison, which is the same condition; the identity is proved by
    `test_widening_both_sides_equals_one_combined_gap`. Doing it in one place keeps the
    query reading raw columns, so it is unaffected by a stale effective snapshot.
    """
    gap = _combined_buffer_gap()
    statement = (
        select(VenueBooking)
        .join(Venue, Venue.id == VenueBooking.venue_id)
        .where(
            VenueBooking.venue_id == booking.venue_id,
            VenueBooking.id != booking.id,
            VenueBooking.start_at < booking.end_at + gap,
            booking.start_at < VenueBooking.end_at + gap,
        )
        .order_by(VenueBooking.start_at, VenueBooking.id)
    )
    return list(db.scalars(statement))


def unavailabilities_overlapping(db: Session, booking: VenueBooking) -> list[VenueUnavailability]:
    """Closures on `booking`'s venue overlapping its period, half-open (SCRUM-73 AC3/AC5).

    SCRUM-82 AC5: the booking is widened by the venue's buffers and the closure is not, so
    preparation that runs into a closure is a clash. Asymmetric on purpose, unlike
    `other_bookings_overlapping`: a closure already covers the whole unusable period.
    """
    statement = (
        select(VenueUnavailability)
        .join(Venue, Venue.id == VenueUnavailability.venue_id)
        .where(
            VenueUnavailability.venue_id == booking.venue_id,
            VenueUnavailability.starts_at < booking.end_at + _turnaround(),
            booking.start_at - _setup() < VenueUnavailability.ends_at,
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
    """Commit a newly confirmed booking or tentative hold (SCRUM-83), translating the
    ADR-0002 exclusion constraint, which covers both since migration 0021.

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
