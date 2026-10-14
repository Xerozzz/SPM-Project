"""Rules for what makes an event request complete enough to submit (SCRUM-46, AC1/AC2).

Pure: the caller passes in the field values and the current time, and gets back a list of
problems, each naming the field it is about. An empty list means the request may be
submitted. Nothing here knows about the database, HTTP, or the ORM (ADR-0003).

Venue requirements remain a fixed vocabulary. Equipment types are supplied by the service
from the catalogue, so this module stays independent of database access.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass, fields
from datetime import datetime

from domain.validation import FieldProblem as FieldProblem

# Order matters only for how problems are reported: it matches the order on the ticket.
REQUIRED_TEXT_FIELDS: tuple[str, ...] = (
    "name",
    "purpose",
    "description",
    "venue_requirement",
    "accessibility_requirement",
    "equipment_requirement",
    "layout_requirement",
    "registration_requirement",
)

EQUIPMENT_REQUIREMENT_FACILITIES: dict[str, str] = {
    "Projector": "Projector",
    "Microphone": "Microphone",
    "PA system": "PA system",
    "Display screen": "Display screen",
}


# SCRUM-36 AC3: the fields an ordinary planning update may change after submission.
# Date/time, expected attendance, venue and equipment requirements are left out on
# purpose: changing any of them can affect venue, equipment and registration arrangements
# already made, so they need change control rather than an ordinary edit.
ORDINARY_FIELDS: tuple[str, ...] = (
    "name",
    "purpose",
    "description",
    "accessibility_requirement",
    "layout_requirement",
    "registration_requirement",
)


@dataclass(frozen=True)
class EventRequestFields:
    """The submittable content of an event request. Everything is optional here because a
    draft may be partially filled in; completeness is what `validate_event_request` checks."""

    name: str | None = None
    purpose: str | None = None
    description: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    expected_attendance: int | None = None
    venue_requirement: str | None = None
    accessibility_requirement: str | None = None
    equipment_requirement: str | None = None
    layout_requirement: str | None = None
    registration_requirement: str | None = None


def validate_catalogue_requirements(
    request: EventRequestFields,
    equipment_types: Collection[str] | None = None,
    venue_names: Collection[str] | None = None,
) -> list[FieldProblem]:
    """Reject requirements outside the catalogue values supplied by the service."""
    problems: list[FieldProblem] = []
    if (
        venue_names is not None
        and not _is_blank(request.venue_requirement)
        and request.venue_requirement not in venue_names
    ):
        problems.append(FieldProblem("venue_requirement", "is not a catalogue option"))
    if not _is_blank(request.equipment_requirement) and request.equipment_requirement not in (
        equipment_types if equipment_types is not None else EQUIPMENT_REQUIREMENT_FACILITIES.keys()
    ):
        problems.append(FieldProblem("equipment_requirement", "is not a catalogue option"))
    return problems


def _is_blank(value: str | None) -> bool:
    return value is None or not value.strip()


def _is_aware(value: datetime) -> bool:
    # AGENTS.md §3: naive datetimes are never accepted at any layer.
    return value.tzinfo is not None and value.tzinfo.utcoffset(value) is not None


def validate_event_request(
    request: EventRequestFields,
    now: datetime,
    equipment_types: Collection[str] | None = None,
    venue_names: Collection[str] | None = None,
) -> list[FieldProblem]:
    """Return every business-rule problem; an empty list means it is complete and valid."""
    problems: list[FieldProblem] = []

    for name in REQUIRED_TEXT_FIELDS:
        if _is_blank(getattr(request, name)):
            problems.append(FieldProblem(name, "is required"))

    problems.extend(validate_catalogue_requirements(request, equipment_types, venue_names))

    problems.extend(_period_problems(request.start_at, request.end_at, now))

    if request.expected_attendance is None:
        problems.append(FieldProblem("expected_attendance", "is required"))
    elif request.expected_attendance <= 0:
        problems.append(FieldProblem("expected_attendance", "must be a positive number"))

    return problems


def _period_problems(
    start_at: datetime | None, end_at: datetime | None, now: datetime
) -> list[FieldProblem]:
    problems: list[FieldProblem] = []

    if start_at is None:
        problems.append(FieldProblem("start_at", "is required"))
    elif not _is_aware(start_at):
        problems.append(FieldProblem("start_at", "must include a timezone"))
    elif start_at <= now:
        problems.append(FieldProblem("start_at", "must be in the future"))

    if end_at is None:
        problems.append(FieldProblem("end_at", "is required"))
    elif not _is_aware(end_at):
        problems.append(FieldProblem("end_at", "must include a timezone"))
    elif start_at is not None and _is_aware(start_at) and end_at <= start_at:
        problems.append(FieldProblem("end_at", "must be after the start"))

    return problems


def field_names() -> tuple[str, ...]:
    """Every submittable field, in ticket order — used by callers that copy values across."""
    return tuple(f.name for f in fields(EventRequestFields))


def validate_ordinary_update(changes: Mapping[str, str | None]) -> list[FieldProblem]:
    """SCRUM-36 AC2: problems with an ordinary update, one per field. Empty means valid.

    Every ordinary field is required for a request to be submitted (SCRUM-46), so once
    submitted an update may change one but never blank it. Only sent fields are checked.
    """
    return [
        FieldProblem(name, "is required")
        for name in ORDINARY_FIELDS
        if name in changes and _is_blank(changes[name])
    ]
