"""Venue suitability check (SCRUM-56).

Pure: the caller passes an event's needs and a venue's facts, and gets back what
the Coordinator needs to judge fit. Nothing here knows about the database, HTTP,
or the ORM (ADR-0003), so every rule is covered by fast unit tests.

Capacity and facilities produce warnings; accessibility and layout needs never
auto-reject — the venue's recorded values are returned alongside the event's
stated needs for the Coordinator to assess (AC3/AC4).

`mismatch_codes` is deliberately a separate vocabulary from
`domain.validation.FieldProblem`: a `FieldProblem` means "this cannot be saved",
while a mismatch code is advisory — the booking can still proceed, but the
Coordinator should see the warning first.
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
    """Everything the Coordinator needs to judge fit.

        Each pair records both sides — what was asked for and what the venue
    offers — so the caller (SCRUM-38) does not have to carry the event's needs
    separately and pair them back up itself.
    """

    mismatch_codes: list[str]
    expected_attendance: int
    venue_capacity: int
    unavailable_facilities: list[str]
    accessibility_need: str | None
    venue_accessibility: list[str]
    layout_need: str | None
    venue_layouts: list[str]


def evaluate_suitability(event: SuitabilityEvent, venue: SuitabilityVenue) -> SuitabilityResult:
    """Check an event against a venue; capacity/facility issues warn, never block."""
    mismatch_codes: list[str] = []
    if event.expected_attendance > venue.maximum_capacity:
        mismatch_codes.append(CAPACITY_EXCEEDED)

    # Facilities are free text on both sides (domain/venue.py), so compare on a
    # trimmed, casefolded key to avoid false "missing" warnings from casing or
    # stray whitespace. Report each missing facility once, keeping the first
    # spelling the event used (stripped) for display.
    offered = {f.strip().casefold() for f in venue.facilities}
    unavailable: list[str] = []
    seen: set[str] = set()
    for raw in event.required_facilities:
        key = raw.strip().casefold()
        if key not in offered and key not in seen:
            seen.add(key)
            unavailable.append(raw.strip())

    return SuitabilityResult(
        mismatch_codes=mismatch_codes,
        expected_attendance=event.expected_attendance,
        venue_capacity=venue.maximum_capacity,
        unavailable_facilities=unavailable,
        accessibility_need=event.accessibility_need,
        venue_accessibility=list(venue.accessibility_features),
        layout_need=event.layout_need,
        venue_layouts=list(venue.supported_layouts),
    )
