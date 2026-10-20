"""Rules for an Organiser's significant-change request (SCRUM-37). Pure, no database.

After submission the Organiser no longer edits the event (ADR-0028). A change to the
date, attendance, venue, sessions or equipment, or to a layout or accessibility need that
affects arrangements, is proposed instead. The proposal keeps the current value next to
each proposed one so the assigned Coordinator can compare them (AC3), and SCRUM-47 later
decides it. Proposing changes nothing on the event itself (AC5).

`plan_change` checks a proposal against the event's current plan and turns it into one
`ChangeItem` per changed value. Each value is checked with the same rule normal creation
and planning use (AC4), so this module reuses those rules rather than restating them.
"""

import uuid
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from domain.equipment_requirement import (
    RequirementFields,
    validate_change,
    validate_new_requirement,
)
from domain.event_status import EventStatus
from domain.validation import FieldProblem
from domain.venue_session import session_problems


class ChangeRequestStatus(StrEnum):
    """Where a change request is. SCRUM-47 adds the decisions."""

    PENDING = "pending"


class ChangeTarget(StrEnum):
    """What a change item changes: the event itself, one session, or one equipment line."""

    EVENT = "event"
    SESSION = "session"
    EQUIPMENT = "equipment"


# AC1 and AC7: submitted, in planning or confirmed. Draft and Rejected events are still
# the Organiser's to edit and resubmit directly (SCRUM-29), so they never need this flow.
PROPOSABLE_STATUSES: frozenset[EventStatus] = frozenset(
    {EventStatus.SUBMITTED, EventStatus.APPROVED, EventStatus.CONFIRMED}
)

# AC2: the event's own fields a significant change may touch. Name, purpose, description
# and registration are ordinary information, kept by the Coordinator (SCRUM-36).
EVENT_FIELDS: tuple[str, ...] = (
    "start_at",
    "end_at",
    "expected_attendance",
    "venue_requirement",
    "accessibility_requirement",
    "layout_requirement",
)

# Removing a line and adding one are changes to the line as a whole, not to one value.
REMOVE = "remove"
ADD = "add"


def accepts_change_request(status: EventStatus) -> bool:
    """AC1/AC7: True when an event in `status` may receive a significant-change request."""
    return status in PROPOSABLE_STATUSES


@dataclass(frozen=True)
class PlannedSession:
    """One live venue request of the event, as it stands now."""

    id: uuid.UUID
    session_label: str
    start_at: datetime
    end_at: datetime


@dataclass(frozen=True)
class Requirement:
    """One live equipment line of the event, as it stands now."""

    id: uuid.UUID
    equipment_type: str
    quantity: int
    technical_requirements: str | None


@dataclass(frozen=True)
class CurrentPlan:
    """The values a proposal is compared against. `event` holds every EVENT_FIELDS value."""

    event: Mapping[str, object]
    sessions: tuple[PlannedSession, ...]
    equipment: tuple[Requirement, ...]


@dataclass(frozen=True)
class SessionProposal:
    """New values for one session. A field left as None is not being changed."""

    booking_id: uuid.UUID
    session_label: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None


@dataclass(frozen=True)
class EquipmentProposal:
    """Add a line (no `requirement_id`), change one, or remove one (`remove=True`)."""

    requirement_id: uuid.UUID | None = None
    equipment_type: str | None = None
    quantity: int | None = None
    technical_requirements: str | None = None
    remove: bool = False


@dataclass(frozen=True)
class Proposal:
    """What the Organiser sent. `event` holds only the fields they want to change."""

    reason: str
    event: Mapping[str, object] = field(default_factory=dict)
    sessions: tuple[SessionProposal, ...] = ()
    equipment: tuple[EquipmentProposal, ...] = ()


@dataclass(frozen=True)
class ChangeItem:
    """One proposed change, with the value it would replace (AC3)."""

    target: ChangeTarget
    target_id: uuid.UUID | None
    field: str
    current: object
    proposed: object


@dataclass(frozen=True)
class Catalogue:
    """The choices the catalogue offers today, supplied by the service."""

    venue_names: Collection[str]
    equipment_types: frozenset[str]


def plan_change(
    proposal: Proposal, current: CurrentPlan, catalogue: Catalogue, now: datetime
) -> tuple[list[ChangeItem], list[FieldProblem]]:
    """Check `proposal` against `current` and list what it would change.

    Returns the change items and every problem found. Any problem means nothing may be
    recorded (AC4): the caller saves the items only when the problem list is empty.
    """
    problems: list[FieldProblem] = []
    if not proposal.reason.strip():
        problems.append(FieldProblem("reason", "is required"))

    items, event_problems = _event_changes(proposal.event, current.event, catalogue, now)
    problems += event_problems
    start, end = _resulting_period(proposal.event, current.event)

    session_items, session_problems_found = _session_changes(
        proposal.sessions, current.sessions, start, end
    )
    equipment_items, equipment_problems = _equipment_changes(
        proposal.equipment, current.equipment, catalogue.equipment_types
    )
    items += session_items + equipment_items
    problems += session_problems_found + equipment_problems

    if not items and not problems:
        problems.append(FieldProblem("changes", "must propose at least one change"))
    return items, problems


def _event_changes(
    proposed: Mapping[str, object],
    current: Mapping[str, object],
    catalogue: Catalogue,
    now: datetime,
) -> tuple[list[ChangeItem], list[FieldProblem]]:
    items: list[ChangeItem] = []
    problems: list[FieldProblem] = []
    for name in EVENT_FIELDS:
        if name not in proposed or proposed[name] == current.get(name):
            continue
        value = proposed[name]
        reason = _event_value_problem(name, value, catalogue, now)
        if reason:
            problems.append(FieldProblem(f"event.{name}", reason))
        else:
            items.append(ChangeItem(ChangeTarget.EVENT, None, name, current.get(name), value))
    start, end = _resulting_period(proposed, current)
    if (
        not problems
        and ("start_at" in proposed or "end_at" in proposed)
        and not _valid_period(start, end)
    ):
        problems.append(FieldProblem("event.end_at", "must be after the start"))
    return items, problems


def _event_value_problem(
    name: str, value: object, catalogue: Catalogue, now: datetime
) -> str | None:
    """The reason one event value is refused, or None. Same rules as creation (AC4)."""
    if name in ("start_at", "end_at"):
        if not isinstance(value, datetime):
            return "is required"
        if not _is_aware(value):
            return "must include a timezone"
        if name == "start_at" and value <= now:
            return "must be in the future"
        return None
    if name == "expected_attendance":
        # `bool` is an `int`; True would otherwise pass as an attendance of one.
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            return "must be a positive whole number"
        return None
    if not isinstance(value, str) or not value.strip():
        return "is required"
    if name == "venue_requirement" and value not in catalogue.venue_names:
        return "is not a catalogue option"
    return None


def _resulting_period(
    proposed: Mapping[str, object], current: Mapping[str, object]
) -> tuple[object, object]:
    """The event period if the proposal were applied."""
    return (
        proposed.get("start_at", current.get("start_at")),
        proposed.get("end_at", current.get("end_at")),
    )


def _session_changes(
    proposals: tuple[SessionProposal, ...],
    sessions: tuple[PlannedSession, ...],
    event_start: object,
    event_end: object,
) -> tuple[list[ChangeItem], list[FieldProblem]]:
    items: list[ChangeItem] = []
    problems: list[FieldProblem] = []
    by_id = {session.id: session for session in sessions}
    proposed_ids = [p.booking_id for p in proposals]
    if not _valid_period(event_start, event_end):
        # The event period itself is refused, and that problem is already reported.
        # Sessions can only be checked against a valid period.
        return items, problems
    assert isinstance(event_start, datetime) and isinstance(event_end, datetime)
    for index, proposal in enumerate(proposals):
        where = f"sessions[{index}]"
        session = by_id.get(proposal.booking_id)
        if session is None:
            problems.append(FieldProblem(f"{where}.booking_id", "is not a session of this event"))
            continue
        if proposed_ids.count(proposal.booking_id) > 1:
            problems.append(FieldProblem(f"{where}.booking_id", "is proposed more than once"))
            continue
        label = proposal.session_label
        if label is None:
            label = session.session_label
        start = proposal.start_at or session.start_at
        end = proposal.end_at or session.end_at
        found = session_problems(label, start, end, event_start, event_end)
        problems += [FieldProblem(f"{where}.{p.field}", p.reason) for p in found]
        if found:
            continue
        for name, old, new in (
            ("session_label", session.session_label, label),
            ("start_at", session.start_at, start),
            ("end_at", session.end_at, end),
        ):
            if new != old:
                items.append(ChangeItem(ChangeTarget.SESSION, session.id, name, old, new))
    # AC4: a new event period must still hold every session the proposal leaves alone.
    for session in sessions:
        if session.id in proposed_ids:
            continue
        if session.start_at < event_start or session.end_at > event_end:
            problems.append(
                FieldProblem(
                    f"sessions.{session.id}",
                    f"session '{session.session_label}' would fall outside the event period",
                )
            )
    return items, problems


def _equipment_changes(
    proposals: tuple[EquipmentProposal, ...],
    lines: tuple[Requirement, ...],
    catalogue_types: frozenset[str],
) -> tuple[list[ChangeItem], list[FieldProblem]]:
    items: list[ChangeItem] = []
    problems: list[FieldProblem] = []
    by_id = {line.id: line for line in lines}
    removed = {p.requirement_id for p in proposals if p.remove}
    # A type freed by a removal in the same proposal may be added again.
    taken = {line.equipment_type for line in lines if line.id not in removed}
    seen_ids: set[uuid.UUID] = set()
    for index, proposal in enumerate(proposals):
        where = f"equipment[{index}]"
        if proposal.requirement_id is None:
            found = validate_new_requirement(
                RequirementFields(
                    proposal.equipment_type, proposal.quantity, proposal.technical_requirements
                ),
                catalogue_types,
                frozenset(taken),
            )
            problems += [FieldProblem(f"{where}.{p.field}", p.reason) for p in found]
            if not found and proposal.equipment_type is not None:
                taken.add(proposal.equipment_type.strip())
                added = {
                    "equipment_type": proposal.equipment_type.strip(),
                    "quantity": proposal.quantity,
                    "technical_requirements": proposal.technical_requirements,
                }
                items.append(ChangeItem(ChangeTarget.EQUIPMENT, None, ADD, None, added))
            continue
        line = by_id.get(proposal.requirement_id)
        if line is None:
            problems.append(FieldProblem(f"{where}.requirement_id", "is not a current requirement"))
            continue
        if line.id in seen_ids:
            problems.append(FieldProblem(f"{where}.requirement_id", "is proposed more than once"))
            continue
        seen_ids.add(line.id)
        if proposal.remove:
            items.append(ChangeItem(ChangeTarget.EQUIPMENT, line.id, REMOVE, _line(line), None))
            continue
        quantity = proposal.quantity if proposal.quantity is not None else line.quantity
        technical = (
            proposal.technical_requirements
            if proposal.technical_requirements is not None
            else line.technical_requirements
        )
        found = validate_change(quantity, technical)
        problems += [FieldProblem(f"{where}.{p.field}", p.reason) for p in found]
        if found:
            continue
        for name, old, new in (
            ("quantity", line.quantity, quantity),
            ("technical_requirements", line.technical_requirements, technical),
        ):
            if new != old:
                items.append(ChangeItem(ChangeTarget.EQUIPMENT, line.id, name, old, new))
    return items, problems


def _line(line: Requirement) -> dict[str, object]:
    return {
        "equipment_type": line.equipment_type,
        "quantity": line.quantity,
        "technical_requirements": line.technical_requirements,
    }


def _valid_period(start: object, end: object) -> bool:
    return (
        isinstance(start, datetime)
        and isinstance(end, datetime)
        and _is_aware(start)
        and _is_aware(end)
        and end > start
    )


def _is_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.tzinfo.utcoffset(value) is not None
