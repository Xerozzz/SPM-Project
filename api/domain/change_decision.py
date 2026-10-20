"""Rules for deciding a significant-change request (SCRUM-47). Pure, no database.

The assigned Coordinator approves or rejects a pending request with a note (AC1). Before
an approval is applied, every item is compared with the live plan: if a value the request
was made against has changed since, the request is stale and nothing is applied (AC2).
The proposed values are then checked again with the SCRUM-37 rules, because a value that
was valid when proposed (a start date, a venue) may not be valid now.

Approval applies the event's own fields (AC3). A session or equipment item is marked as
needing replanning instead: the venue and equipment flows decide those, so a confirmed
booking or reservation is never moved silently (AC4, AC8).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import cast

from domain.event_change import (
    ADD,
    REMOVE,
    ChangeRequestStatus,
    ChangeTarget,
    CurrentPlan,
    EquipmentProposal,
    PlannedSession,
    Proposal,
    Requirement,
    SessionProposal,
)
from domain.validation import FieldProblem


class Decision(StrEnum):
    """What the Coordinator decides."""

    APPROVE = "approve"
    REJECT = "reject"


class ItemOutcome(StrEnum):
    """What an approval did with one item."""

    APPLIED = "applied"
    NEEDS_REPLANNING = "needs_replanning"


class AlreadyDecidedError(Exception):
    """AC9: a request is decided once. A repeat decision changes nothing."""

    def __init__(self, status: str) -> None:
        super().__init__(f"this change request is already {status}")
        self.status = status


@dataclass(frozen=True)
class RecordedItem:
    """One stored item, values as stored (JSON: dates are ISO 8601 text)."""

    target: str
    target_id: object
    field: str
    current_value: object
    proposed_value: object


def decision_problems(status: str, note: str) -> list[FieldProblem]:
    """AC1: a pending request and a non-blank note. Raises if already decided (AC9)."""
    if status != ChangeRequestStatus.PENDING:
        raise AlreadyDecidedError(status)
    if not note.strip():
        return [FieldProblem("note", "is required")]
    return []


def decided_status(decision: Decision) -> ChangeRequestStatus:
    if decision is Decision.APPROVE:
        return ChangeRequestStatus.APPROVED
    return ChangeRequestStatus.REJECTED


def stale_items(items: Sequence[RecordedItem], current: CurrentPlan) -> list[FieldProblem]:
    """AC2: every item whose recorded current value no longer matches the live plan."""
    problems: list[FieldProblem] = []
    for index, item in enumerate(items):
        if _live_value(item, current) != item.current_value:
            problems.append(
                FieldProblem(f"items[{index}]", "has changed since the request was made")
            )
    return problems


def proposal_of(reason: str, items: Sequence[RecordedItem]) -> Proposal:
    """Rebuild what was proposed, so it can be checked again against today's rules."""
    event: dict[str, object] = {}
    sessions: dict[object, dict[str, object]] = {}
    lines: dict[object, dict[str, object]] = {}
    equipment: list[EquipmentProposal] = []
    for item in items:
        value = item.proposed_value
        if item.target == ChangeTarget.EVENT:
            event[item.field] = _from_json(item.field, value)
        elif item.target == ChangeTarget.SESSION:
            sessions.setdefault(item.target_id, {})[item.field] = _from_json(item.field, value)
        elif item.field == ADD:
            line = cast(dict[str, object], value)
            equipment.append(
                EquipmentProposal(
                    equipment_type=cast(str, line["equipment_type"]),
                    quantity=cast(int, line["quantity"]),
                    technical_requirements=cast(str | None, line["technical_requirements"]),
                )
            )
        elif item.field == REMOVE:
            lines[item.target_id] = {"remove": True}
        else:
            lines.setdefault(item.target_id, {})[item.field] = value
    session_proposals = tuple(
        SessionProposal(
            booking_id=cast(uuid.UUID, key),
            session_label=cast(str | None, values.get("session_label")),
            start_at=cast(datetime | None, values.get("start_at")),
            end_at=cast(datetime | None, values.get("end_at")),
        )
        for key, values in sessions.items()
    )
    equipment_changes = tuple(
        EquipmentProposal(
            requirement_id=cast(uuid.UUID, key),
            quantity=cast(int | None, values.get("quantity")),
            technical_requirements=cast(str | None, values.get("technical_requirements")),
            remove=bool(values.get("remove", False)),
        )
        for key, values in lines.items()
    )
    return Proposal(
        reason=reason,
        event=event,
        sessions=session_proposals,
        equipment=equipment_changes + tuple(equipment),
    )


def outcome_of(item: RecordedItem) -> ItemOutcome:
    """AC3/AC4: the event's own fields are applied, arrangements need replanning."""
    if item.target == ChangeTarget.EVENT:
        return ItemOutcome.APPLIED
    return ItemOutcome.NEEDS_REPLANNING


def event_value(item: RecordedItem) -> object:
    """The proposed event value, as the event stores it."""
    return _from_json(item.field, item.proposed_value)


def _live_value(item: RecordedItem, current: CurrentPlan) -> object:
    if item.target == ChangeTarget.EVENT:
        return _to_json(current.event.get(item.field))
    if item.target == ChangeTarget.SESSION:
        session = _find(current.sessions, item.target_id)
        if session is None:
            return _GONE
        return _to_json(getattr(session, item.field))
    if item.field == ADD:
        return None
    line = _find(current.equipment, item.target_id)
    if line is None:
        return _GONE
    if item.field == REMOVE:
        return {
            "equipment_type": line.equipment_type,
            "quantity": line.quantity,
            "technical_requirements": line.technical_requirements,
        }
    return getattr(line, item.field)


# A record that no longer exists never equals a recorded value, so its item is stale.
_GONE = object()


def _find[T: (PlannedSession, Requirement)](records: Sequence[T], record_id: object) -> T | None:
    return next((r for r in records if str(r.id) == str(record_id)), None)


def _to_json(value: object) -> object:
    return value.isoformat() if isinstance(value, datetime) else value


def _from_json(field: str, value: object) -> object:
    if field.endswith("_at") and isinstance(value, str):
        return datetime.fromisoformat(value)
    return value
