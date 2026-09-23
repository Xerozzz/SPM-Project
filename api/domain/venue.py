"""Rules for what makes a venue record valid (SCRUM-59, AC1 and AC5).

Pure: the caller passes the field values and gets back a list of problems, each naming the
field it is about. An empty list means the record may be saved. Nothing here knows about
the database, HTTP, or the ORM (ADR-0003), so every rule below is covered by fast unit
tests rather than by standing up an API.

Operating hours are wall-clock times, not instants: "this hall opens at 08:00" is true
whatever the date. That is why they are `time` and not `datetime`, and why AGENTS.md's
timezone-aware-UTC rule does not apply to them; it governs points in time, which a venue's
opening hour is not.
"""

from dataclasses import dataclass, fields
from datetime import time

from domain.validation import FieldProblem

# Order matters only for how problems are reported: it matches the order on the ticket.
REQUIRED_TEXT_FIELDS: tuple[str, ...] = ("name", "location")

# A closed vocabulary so a coordinator searching for "classroom" matches every venue that
# supports it. Facilities and accessibility features stay free text on purpose: the customer
# said venue suitability is the coordinator's judgement, not an automatic flag.
ROOM_LAYOUTS: tuple[str, ...] = (
    "theatre",
    "classroom",
    "banquet",
    "boardroom",
    "u_shape",
    "standing",
)


@dataclass(frozen=True)
class VenueFields:
    """The content of a venue record. Everything is optional here because the caller may
    be part-way through filling a form; completeness is what `validate_venue` checks."""

    name: str | None = None
    location: str | None = None
    maximum_capacity: int | None = None
    facilities: list[str] | None = None
    supported_layouts: list[str] | None = None
    accessibility_features: list[str] | None = None
    opens_at: time | None = None
    closes_at: time | None = None


def field_names() -> tuple[str, ...]:
    """Every venue field, in ticket order, for callers that copy values across."""
    return tuple(f.name for f in fields(VenueFields))


def _is_blank(value: str | None) -> bool:
    return value is None or not value.strip()


def validate_venue(venue: VenueFields) -> list[FieldProblem]:
    """Return every problem that blocks saving; an empty list means it may be saved."""
    problems: list[FieldProblem] = []

    for name in REQUIRED_TEXT_FIELDS:
        if _is_blank(getattr(venue, name)):
            problems.append(FieldProblem(name, "is required"))

    problems.extend(_capacity_problems(venue.maximum_capacity))
    problems.extend(_layout_problems(venue.supported_layouts))
    problems.extend(_operating_hours_problems(venue.opens_at, venue.closes_at))

    return problems


def _capacity_problems(maximum_capacity: int | None) -> list[FieldProblem]:
    if maximum_capacity is None:
        return [FieldProblem("maximum_capacity", "is required")]
    # A venue that seats nobody cannot host an event, so one is the smallest real capacity.
    if maximum_capacity < 1:
        return [FieldProblem("maximum_capacity", "must be at least 1")]
    return []


def _layout_problems(supported_layouts: list[str] | None) -> list[FieldProblem]:
    if not supported_layouts:
        return [FieldProblem("supported_layouts", "is required")]
    unknown = [layout for layout in supported_layouts if layout not in ROOM_LAYOUTS]
    if unknown:
        return [
            FieldProblem(
                "supported_layouts",
                f"must be chosen from the catalogue layouts: {', '.join(ROOM_LAYOUTS)}",
            )
        ]
    return []


def _operating_hours_problems(opens_at: time | None, closes_at: time | None) -> list[FieldProblem]:
    problems: list[FieldProblem] = []

    if opens_at is None:
        problems.append(FieldProblem("opens_at", "is required"))
    if closes_at is None:
        problems.append(FieldProblem("closes_at", "is required"))
    # A venue that closes when it opens is open for no time at all, so equal is invalid too.
    # Overnight hours (closing after midnight) are out of scope for this release.
    elif opens_at is not None and closes_at <= opens_at:
        problems.append(FieldProblem("closes_at", "must be after the opening time"))

    return problems
