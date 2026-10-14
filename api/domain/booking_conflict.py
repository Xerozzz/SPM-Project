"""Venue booking approval conflicts (SCRUM-73).

Pure: no I/O. Callers (services/venue_bookings.py) supply the request's period and the
venue's other bookings and unavailability blocks; this module decides whether any of
them blocks approval, and names the one that does.

Periods are compared as effective occupied intervals (SCRUM-82): the venue's setup and
turnaround widen a booking, so the comparisons live in `domain.venue_buffer` and the
half-open [start, end) rule underneath them is `domain.venue_search.intervals_overlap`,
reused rather than restated, so venue search and booking approval cannot disagree about
whether back-to-back periods clash. With no buffers an effective interval is the event's
own period, so a venue without buffers behaves exactly as it did before SCRUM-82 (AC7).

This check gives a friendly, named refusal; the database exclusion constraint from
ADR-0002 (SCRUM-74, ADR-0017, widened to effective intervals by ADR-0019) is what
guarantees it under concurrency, and `ConcurrentBookingConflictError` reports a violation.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from domain.venue_booking import BookingStatus
from domain.venue_buffer import VenueBuffers, booking_clashes_with_closure, bookings_clash
from domain.venue_search import booking_blocks_availability


@dataclass(frozen=True)
class BookedPeriod:
    """Another booking on the same venue, as far as the conflict rule needs to know."""

    id: UUID
    status: BookingStatus
    start_at: datetime
    end_at: datetime


@dataclass(frozen=True)
class UnavailablePeriod:
    """A recorded venue closure (SCRUM-62)."""

    id: UUID
    starts_at: datetime
    ends_at: datetime


class BookingConflictError(Exception):
    """Base for every reason a booking request cannot be approved."""


class ConflictingBookingError(BookingConflictError):
    """AC1: a confirmed booking, or since SCRUM-83 a tentative hold, already holds an
    overlapping period. The message says which of the two it is."""

    def __init__(self, booking: BookedPeriod) -> None:
        held = booking.status is BookingStatus.TENTATIVE
        what = "tentative hold" if held else "confirmed booking"
        super().__init__(f"conflicts with {what} {booking.id}")
        self.booking = booking


class ConcurrentBookingConflictError(BookingConflictError):
    """SCRUM-74 AC1: the friendly check passed, but another approval for an overlapping
    period committed first and the database exclusion constraint refused this one."""

    def __init__(self) -> None:
        super().__init__("conflicts with a booking confirmed at the same time")


class VenueUnavailableError(BookingConflictError):
    """AC3: the venue is closed for part of the requested period."""

    def __init__(self, period: UnavailablePeriod) -> None:
        super().__init__(f"venue is unavailable for period {period.id}")
        self.period = period


def ensure_no_conflict(
    start_at: datetime,
    end_at: datetime,
    other_bookings: Iterable[BookedPeriod],
    unavailable_periods: Iterable[UnavailablePeriod],
    buffers: VenueBuffers,
) -> None:
    """Raise if anything blocks approving a booking for [start_at, end_at).

    `start_at` and `end_at` are the event's own times; `buffers` are the venue's, and the
    widening into effective occupied intervals happens here so every caller gets the same
    rule. It is a required argument rather than one defaulting to no buffers, because a
    caller that forgot it would silently go back to the pre-SCRUM-82 behaviour.

    Only a CONFIRMED booking or a TENTATIVE hold blocks (AC4: pending, rejected and
    cancelled never do, SCRUM-83 AC3 for the hold), using the same status rule as venue
    search. Adjacent effective intervals do not
    overlap (AC2, AC5, and SCRUM-82 AC6). When several things clash, the earliest-starting
    one is named, ties broken by lowest id, so the result does not depend on input order.
    Bookings are checked before closures: a clash with another event is the more
    actionable message.
    """
    clashing_bookings = [
        booking
        for booking in other_bookings
        if booking_blocks_availability(booking.status)
        and bookings_clash(start_at, end_at, booking.start_at, booking.end_at, buffers)
    ]
    if clashing_bookings:
        raise ConflictingBookingError(min(clashing_bookings, key=lambda b: (b.start_at, b.id)))

    clashing_closures = [
        period
        for period in unavailable_periods
        # Only the booking is widened: a closure already covers the whole unusable period.
        if booking_clashes_with_closure(start_at, end_at, period.starts_at, period.ends_at, buffers)
    ]
    if clashing_closures:
        raise VenueUnavailableError(min(clashing_closures, key=lambda p: (p.starts_at, p.id)))
