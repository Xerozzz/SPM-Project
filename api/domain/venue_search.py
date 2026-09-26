"""Pure venue-search rules for SCRUM-55.

No I/O, no ORM imports (AGENTS.md section 3). The service layer converts persisted
venues into `SearchableVenue` and delegates every decision here, so the rules are
covered by fast unit tests rather than by standing up an API.
"""

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

from domain.venue_booking import BookingStatus

_ORG_TZ = ZoneInfo("Asia/Singapore")


@dataclass(frozen=True)
class SearchableVenue:
    """The venue attributes that static search criteria compare against."""

    maximum_capacity: int
    location: str
    facilities: list[str]
    accessibility_features: list[str]
    supported_layouts: list[str]


@dataclass(frozen=True)
class VenueSearchCriteria:
    """Every static filter a coordinator may supply. None means "no constraint"."""

    minimum_capacity: int | None = None
    location: str | None = None
    required_facilities: list[str] | None = None
    required_accessibility: list[str] | None = None
    required_layout: str | None = None


def venue_matches_criteria(venue: SearchableVenue, criteria: VenueSearchCriteria) -> bool:
    """Strict matching (SCRUM-55 AC2): every supplied criterion must hold.

    Free text compares on a trimmed, casefolded key (like SCRUM-56 suitability), so
    "projector" matches a venue offering "Projector" and stray whitespace never
    excludes a venue.
    """
    if criteria.minimum_capacity is not None and (
        venue.maximum_capacity < criteria.minimum_capacity
    ):
        return False
    if criteria.location is not None and _key(venue.location) != _key(criteria.location):
        return False
    offered_facilities = {_key(f) for f in venue.facilities}
    for facility in criteria.required_facilities or []:
        if _key(facility) not in offered_facilities:
            return False
    offered_accessibility = {_key(f) for f in venue.accessibility_features}
    for need in criteria.required_accessibility or []:
        if _key(need) not in offered_accessibility:
            return False
    if criteria.required_layout is None:
        return True
    return _key(criteria.required_layout) in {_key(layout) for layout in venue.supported_layouts}


def _key(value: str) -> str:
    """The comparison key for free-text venue attributes."""
    return value.strip().casefold()


def is_within_operating_hours(
    opens_at: time, closes_at: time, requested_start: datetime, requested_end: datetime
) -> bool:
    """AC3: the requested period must fit inside daily opening hours.

    The requested bounds are tz-aware datetimes; they are converted to the
    organisation's local time (Asia/Singapore) before their wall-clock
    time-of-day is compared against the daily hours, because `opens_at` /
    `closes_at` are local wall-clock times (see domain/venue.py), not UTC
    instants. A multi-day request is within hours when its local start
    time-of-day and end time-of-day are both inside. Both boundaries are
    inclusive: ending exactly at closing (or starting exactly at opening) is
    allowed, because the venue is still open at that instant.

    A request that runs through a closed night is outside hours even when both
    endpoints look open: the local end must not be earlier in the day than the
    local start, otherwise the period necessarily crosses closing time.
    """
    for moment in (requested_start, requested_end):
        if moment.tzinfo is None:
            raise ValueError("requested period bounds must be timezone-aware")
    if not requested_start < requested_end:
        return False
    local_start = requested_start.astimezone(_ORG_TZ).time()
    local_end = requested_end.astimezone(_ORG_TZ).time()
    return opens_at <= local_start <= local_end <= closes_at


def intervals_overlap(
    first_start: datetime, first_end: datetime, second_start: datetime, second_end: datetime
) -> bool:
    """Half-open [start, end) overlap: adjacent intervals do not overlap."""
    for moment in (first_start, first_end, second_start, second_end):
        if moment.tzinfo is None:
            raise ValueError("interval bounds must be timezone-aware")
    return max(first_start, second_start) < min(first_end, second_end)


def booking_blocks_availability(status: BookingStatus) -> bool:
    """AC4/AC6: only a confirmed hold blocks search; a pending request does not.

    Takes the closed `BookingStatus` vocabulary (never a bare string), so a typo is a
    type error rather than a venue silently staying visible.
    """
    return status is BookingStatus.CONFIRMED
