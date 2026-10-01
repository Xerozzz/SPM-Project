"""Venue booking approval conflicts (SCRUM-73).

Pure: no I/O. Callers (services/venue_bookings.py) supply the request's period and the
venue's other bookings and unavailability blocks; this module decides whether any of
them blocks approval, and names the one that does.

The half-open [start, end) overlap rule is `domain.venue_search.intervals_overlap`,
reused rather than restated, so venue search and booking approval cannot disagree about
whether back-to-back periods clash. This check gives a friendly, named refusal; the
database exclusion constraint from ADR-0002 is deferred to SCRUM-74 — see
docs/adr/0016-application-booking-conflict-check-before-constraint.md.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from domain.venue_booking import BookingStatus
from domain.venue_search import booking_blocks_availability, intervals_overlap


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
    """AC1: a confirmed booking already holds an overlapping period."""

    def __init__(self, booking: BookedPeriod) -> None:
        super().__init__(f"conflicts with confirmed booking {booking.id}")
        self.booking = booking


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
) -> None:
    """Raise if anything blocks approving a booking for [start_at, end_at).

    Only a CONFIRMED booking blocks (AC4: pending, rejected and cancelled never do),
    using the same status rule as venue search. Adjacent periods do not overlap (AC2,
    AC5). When several things clash, the earliest-starting one is named, ties broken by
    lowest id, so the result does not depend on input order. Bookings are checked
    before closures: a clash with another event is the more actionable message.
    """
    clashing_bookings = [
        booking
        for booking in other_bookings
        if booking_blocks_availability(booking.status)
        and intervals_overlap(start_at, end_at, booking.start_at, booking.end_at)
    ]
    if clashing_bookings:
        raise ConflictingBookingError(min(clashing_bookings, key=lambda b: (b.start_at, b.id)))

    clashing_closures = [
        period
        for period in unavailable_periods
        if intervals_overlap(start_at, end_at, period.starts_at, period.ends_at)
    ]
    if clashing_closures:
        raise VenueUnavailableError(min(clashing_closures, key=lambda p: (p.starts_at, p.id)))
