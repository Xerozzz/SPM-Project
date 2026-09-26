"""Venue suitability check (SCRUM-56).

Pure: the caller passes an event's needs and a venue's facts, and gets back what
the Coordinator needs to judge fit. Nothing here knows about the database, HTTP,
or the ORM (ADR-0003), so every rule is covered by fast unit tests.

Capacity and facilities produce warnings; accessibility and layout needs never
auto-reject — the venue's recorded values are returned for the Coordinator to
assess (AC3/AC4).
"""

from dataclasses import dataclass, field

CAPACITY_EXCEEDED = "CAPACITY_EXCEEDED"


@dataclass(frozen=True)
class SuitabilityEvent:
    """What the event needs. Optional needs default to None (no constraint)."""

    expected_attendance: int
    required_facilities: list[str] = field(default_factory=list)
    accessibility_need: str | None = None
    layout_need: str | None = None


@dataclass(frozen=True)
class SuitabilityVenue:
    """What the venue offers."""

    maximum_capacity: int
    facilities: list[str] = field(default_factory=list)
    accessibility_features: list[str] = field(default_factory=list)
    supported_layouts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SuitabilityResult:
    """Everything the Coordinator needs to judge fit."""

    mismatch_codes: list[str]
    expected_attendance: int
    venue_capacity: int
    unavailable_facilities: list[str]
    venue_accessibility: list[str]
    venue_layouts: list[str]


def evaluate_suitability(event: SuitabilityEvent, venue: SuitabilityVenue) -> SuitabilityResult:
    """Check an event against a venue; capacity/facility issues warn, never block."""
    mismatch_codes: list[str] = []
    if event.expected_attendance > venue.maximum_capacity:
        mismatch_codes.append(CAPACITY_EXCEEDED)

    unavailable = [f for f in event.required_facilities if f not in venue.facilities]

    return SuitabilityResult(
        mismatch_codes=mismatch_codes,
        expected_attendance=event.expected_attendance,
        venue_capacity=venue.maximum_capacity,
        unavailable_facilities=unavailable,
        venue_accessibility=list(venue.accessibility_features),
        venue_layouts=list(venue.supported_layouts),
    )
