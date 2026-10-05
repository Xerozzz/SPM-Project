"""Venue availability calendar (SCRUM-54)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.orm import Session

from domain import venue_calendar
from domain.validation import FieldProblem
from repositories import venue_calendar as repo


class InvalidCalendarRangeError(Exception):
    def __init__(self, problems: list[FieldProblem]) -> None:
        super().__init__("invalid calendar range")
        self.problems = problems


@dataclass(frozen=True)
class CalendarEntry:
    """One thing holding a venue: a booking (confirmed or pending) or a closure."""

    kind: Literal["booking", "unavailability"]
    id: uuid.UUID
    venue_id: uuid.UUID
    venue_name: str
    start_at: datetime
    end_at: datetime
    # "confirmed" or "pending" for a booking (AC1 labels), "unavailable" for a closure.
    status: str


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
        CalendarEntry("booking", b.id, v.id, v.name, b.start_at, b.end_at, b.status.value)
        for b, v in repo.bookings_in_range(db, start_at, end_at, statuses, venue_id)
    ]
    closures = [
        CalendarEntry("unavailability", u.id, v.id, v.name, u.starts_at, u.ends_at, "unavailable")
        for u, v in repo.unavailabilities_in_range(db, start_at, end_at, venue_id)
    ]
    return sorted(bookings + closures, key=lambda entry: (entry.start_at, str(entry.id)))
