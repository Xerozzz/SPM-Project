"""Venue availability calendar (SCRUM-54) and availability check (SCRUM-76)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from domain import venue_calendar
from domain.validation import FieldProblem
from repositories import venue_calendar as repo
from services import venues


class InvalidCalendarRangeError(Exception):
    def __init__(self, problems: list[FieldProblem]) -> None:
        super().__init__("invalid calendar range")
        self.problems = problems


@dataclass(frozen=True)
class CalendarEntry:
    """One thing holding a venue: a booking (confirmed or pending) or a closure."""

    kind: venue_calendar.EntryKind
    id: uuid.UUID
    venue_id: uuid.UUID
    venue_name: str
    start_at: datetime
    end_at: datetime
    # "confirmed" or "pending" for a booking (AC1 labels), "unavailable" for a closure.
    status: venue_calendar.EntryStatus


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
        )
        for b, v in repo.bookings_in_range(db, start_at, end_at, statuses, venue_id)
    ]
    closures = [
        CalendarEntry("unavailability", u.id, v.id, v.name, u.starts_at, u.ends_at, "unavailable")
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
    """AC1 to AC3: unavailable if a confirmed booking or a closure overlaps the period.
    Pending requests are still listed (AC2) but do not make the venue unavailable.
    A deactivated venue is never available, the same as in venue search (ADR-0012).

    `available` means nothing is holding the venue. Opening hours are not considered,
    so a venue can be reported available for a period it is closed (unlike venue search).
    """
    venue = venues.get(db, venue_id)
    found = entries(db, start_at, end_at, venue_id)
    blocked = any(venue_calendar.entry_blocks(entry.kind, entry.status) for entry in found)
    available = venue.is_active and not blocked
    return Availability(
        venue_id, start_at.astimezone(UTC), end_at.astimezone(UTC), available, found
    )
