"""Venue availability calendar (SCRUM-54), availability check (SCRUM-76) and entry
details (SCRUM-77)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from domain import venue_calendar
from domain.validation import FieldProblem
from domain.venue_buffer import VenueBuffers, effective_interval
from models.venue import Venue
from repositories import venue_calendar as repo
from services import venues


class CalendarEntryNotFoundError(Exception):
    pass


class InvalidCalendarRangeError(Exception):
    def __init__(self, problems: list[FieldProblem]) -> None:
        super().__init__("invalid calendar range")
        self.problems = problems


@dataclass(frozen=True)
class CalendarEntry:
    """One thing holding a venue: a booking (confirmed, tentative or pending) or a
    closure."""

    kind: venue_calendar.EntryKind
    id: uuid.UUID
    venue_id: uuid.UUID
    venue_name: str
    start_at: datetime
    end_at: datetime
    # "confirmed", "tentative" or "pending" for a booking (AC1 labels, SCRUM-83 AC2),
    # "unavailable" for a closure.
    status: venue_calendar.EntryStatus
    effective_start_at: datetime
    effective_end_at: datetime
    # SCRUM-111: which session of the parent event a booking entry is for.
    # None for a closure, which belongs to no session.
    session_label: str | None = None
    # SCRUM-83 AC2: when a tentative hold ends. None for anything else.
    expires_at: datetime | None = None


def _buffers_of(venue: Venue) -> VenueBuffers:
    """SCRUM-82: a venue's current buffers, as the domain takes them."""
    return VenueBuffers(
        setup_minutes=venue.setup_minutes, turnaround_minutes=venue.turnaround_minutes
    )


def entries(
    db: Session, start_at: datetime, end_at: datetime, venue_id: uuid.UUID | None = None
) -> list[CalendarEntry]:
    """AC1 and AC2: everything holding the venue (or every venue) in the range, by start."""
    problems = venue_calendar.range_problems(start_at, end_at)
    if problems:
        raise InvalidCalendarRangeError(problems)
    start_at, end_at = start_at.astimezone(UTC), end_at.astimezone(UTC)
    statuses = venue_calendar.SHOWN_BOOKING_STATUSES
    bookings = [
        CalendarEntry(
            "booking",
            b.id,
            v.id,
            v.name,
            b.start_at,
            b.end_at,
            venue_calendar.BOOKING_LABELS[b.status],
            *effective_interval(b.start_at, b.end_at, _buffers_of(v)),
            session_label=b.session_label,
            expires_at=b.expires_at,
        )
        for b, v in repo.bookings_in_range(db, start_at, end_at, statuses, venue_id)
    ]
    closures = [
        CalendarEntry(
            "unavailability",
            u.id,
            v.id,
            v.name,
            u.starts_at,
            u.ends_at,
            "unavailable",
            u.starts_at,
            u.ends_at,
        )
        for u, v in repo.unavailabilities_in_range(db, start_at, end_at, venue_id)
    ]
    return sorted(bookings + closures, key=lambda entry: (entry.start_at, str(entry.id)))


@dataclass(frozen=True)
class Availability:
    """SCRUM-76: whether one venue is free for a period, and what is there."""

    venue_id: uuid.UUID
    start_at: datetime
    end_at: datetime
    available: bool
    entries: list[CalendarEntry]


def availability(
    db: Session, venue_id: uuid.UUID, start_at: datetime, end_at: datetime
) -> Availability:
    """AC1 to AC3: unavailable if a confirmed booking, a tentative hold (SCRUM-83 AC3) or a
    closure overlaps the period.
    Pending requests are still listed (AC2) but do not make the venue unavailable.
    A deactivated venue is never available, the same as in venue search (ADR-0012).

    `available` means nothing is holding the venue. Opening hours are not considered,
    so a venue can be reported available for a period it is closed (unlike venue search).

    SCRUM-82 AC4: the period asked about is a period someone wants to *use* the venue for,
    so it is widened by the venue's buffers before anything is compared, the same reading
    venue search takes. The entries themselves are widened by `repo.bookings_in_range`, so
    a booking is compared effective-to-effective (AC6) and a closure only against the
    widened request (AC5).

    `entries` reports what was found over the widened period, because those are the
    entries behind the answer: with buffers, a booking whose event sits just outside the
    requested period can still be the reason the venue is not free, and leaving it out
    would show an unavailable venue with nothing to explain it.
    """
    venue = venues.get(db, venue_id)
    buffers = _buffers_of(venue)
    occupied_start, occupied_end = effective_interval(start_at, end_at, buffers)
    found = entries(db, occupied_start, occupied_end, venue_id)
    blocked = any(venue_calendar.entry_blocks(entry.kind, entry.status) for entry in found)
    available = venue.is_active and not blocked
    return Availability(
        venue_id, start_at.astimezone(UTC), end_at.astimezone(UTC), available, found
    )


@dataclass(frozen=True)
class EntryDetails:
    """SCRUM-77 AC1: venue, start, end and status of one entry, and a closure's reason.

    For a booking only the event's id is given. Its details come from the event request
    endpoint, which applies require_event_access(VIEW), so they are shown only to users
    allowed to see that event (AC2, AC3).
    """

    kind: venue_calendar.EntryKind
    id: uuid.UUID
    venue_id: uuid.UUID
    venue_name: str
    venue_location: str
    start_at: datetime
    end_at: datetime
    status: venue_calendar.DetailsStatus
    reason: str | None
    event_request_id: uuid.UUID | None
    # SCRUM-83 AC2: when a tentative hold ends, kept after it ends.
    expires_at: datetime | None = None
    # SCRUM-111: which session of the parent event a booking entry is for.
    session_label: str | None = None


def booking_details(db: Session, booking_id: uuid.UUID) -> EntryDetails:
    row = repo.booking_with_venue(db, booking_id)
    if row is None:
        raise CalendarEntryNotFoundError
    b, v = row
    return EntryDetails(
        "booking",
        b.id,
        v.id,
        v.name,
        v.location,
        b.start_at,
        b.end_at,
        venue_calendar.DETAILS_LABELS[b.status],
        None,
        b.event_request_id,
        b.expires_at,
        b.session_label,
    )


def unavailability_details(db: Session, unavailability_id: uuid.UUID) -> EntryDetails:
    row = repo.unavailability_with_venue(db, unavailability_id)
    if row is None:
        raise CalendarEntryNotFoundError
    u, v = row
    return EntryDetails(
        "unavailability",
        u.id,
        v.id,
        v.name,
        v.location,
        u.starts_at,
        u.ends_at,
        "unavailable",
        u.reason,
        None,
    )
