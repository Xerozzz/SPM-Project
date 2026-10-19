"""Equipment requirement persistence (SCRUM-43, SCRUM-44)."""

import uuid
from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from models.equipment_requirement_change import EquipmentRequirementChange
from models.event_equipment_requirement import EventEquipmentRequirement
from models.event_request import EventRequest


def list_for_event(
    db: Session, event_request_id: uuid.UUID, *, include_removed: bool = False
) -> list[EventEquipmentRequirement]:
    """An event's requirements, oldest first.

    Removed ones are left out by default: AC7 keeps them identifiable in the history but
    says they no longer count, so a caller has to ask for them on purpose.
    """
    statement = select(EventEquipmentRequirement).where(
        EventEquipmentRequirement.event_request_id == event_request_id
    )
    if not include_removed:
        statement = statement.where(EventEquipmentRequirement.removed_at.is_(None))
    return list(
        db.scalars(
            statement.order_by(EventEquipmentRequirement.created_at, EventEquipmentRequirement.id)
        )
    )


def live_for_events(
    db: Session, event_request_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, list[EventEquipmentRequirement]]:
    """The live requirements of several events at once, keyed by event, oldest first.

    One query rather than one per event: the Venue Staff queue lists every pending
    booking at every venue, so asking per row would be an N+1 that grows with the
    backlog. Events with nothing required are absent from the result, so callers use
    `.get(id, [])` rather than expecting a key.
    """
    if not event_request_ids:
        return {}
    statement = (
        select(EventEquipmentRequirement)
        .where(
            EventEquipmentRequirement.event_request_id.in_(event_request_ids),
            EventEquipmentRequirement.removed_at.is_(None),
        )
        .order_by(EventEquipmentRequirement.created_at, EventEquipmentRequirement.id)
    )
    found: dict[uuid.UUID, list[EventEquipmentRequirement]] = {}
    for row in db.scalars(statement):
        found.setdefault(row.event_request_id, []).append(row)
    return found


def get(db: Session, requirement_id: uuid.UUID) -> EventEquipmentRequirement | None:
    return db.get(EventEquipmentRequirement, requirement_id)


def live_types_for_event(
    db: Session, event_request_id: uuid.UUID, *, excluding: uuid.UUID | None = None
) -> frozenset[str]:
    """The types this event already asks for, for the duplicate rule (AC4).

    `excluding` leaves out the requirement being edited, so keeping its own type is not
    read as a collision with itself.
    """
    return frozenset(
        row.equipment_type
        for row in list_for_event(db, event_request_id)
        if excluding is None or row.id != excluding
    )


# AC4 is checked in the domain before the insert, but that is a read followed by a write:
# two coordinators adding the same type at the same moment both pass it. The partial unique
# index is what actually guarantees it, so the loser has to be turned back into the same
# refusal the check would have given rather than escaping as a 500.
DUPLICATE_LIVE_TYPE_INDEX = "event_equipment_requirements_one_live_line_per_type"


class DuplicateRequirementError(Exception):
    """The database refused a second live line for one type on one event (AC4)."""


def save(db: Session, requirement: EventEquipmentRequirement) -> EventEquipmentRequirement:
    """Commit the requirement and any audit row added alongside it.

    Same shape as `repositories.equipment.save`, which has the same read-then-write race
    on its own uniqueness.
    """
    db.add(requirement)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if _violates_one_live_line_per_type(exc):
            raise DuplicateRequirementError from exc
        raise
    db.refresh(requirement)
    return requirement


def _violates_one_live_line_per_type(error: IntegrityError) -> bool:
    constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
    return constraint == DUPLICATE_LIVE_TYPE_INDEX


def record_change(db: Session, change: EquipmentRequirementChange) -> None:
    """Add an audit row to the session. The caller's save commits it (AC8, ADR-0027)."""
    db.add(change)


def changes_for_event(db: Session, event_request_id: uuid.UUID) -> list[EquipmentRequirementChange]:
    """The event's requirement history, oldest first (AC7, AC8)."""
    statement = (
        select(EquipmentRequirementChange)
        .where(EquipmentRequirementChange.event_request_id == event_request_id)
        .order_by(EquipmentRequirementChange.changed_at, EquipmentRequirementChange.id)
    )
    return list(db.scalars(statement))


def list_for_review(db: Session) -> list[tuple[EventEquipmentRequirement, EventRequest]]:
    """SCRUM-44 AC1: every live requirement of an event in planning, with its event.

    Soonest event first, so the one that has to be arranged first is at the top. Events
    without a start time sort last rather than vanishing.
    """
    statement = (
        select(EventEquipmentRequirement, EventRequest)
        .join(EventRequest, EventRequest.id == EventEquipmentRequirement.event_request_id)
        .where(
            EventRequest.status == EventStatus.APPROVED,
            EventEquipmentRequirement.removed_at.is_(None),
        )
        .order_by(
            EventRequest.start_at.asc().nulls_last(),
            EventRequest.id,
            EventEquipmentRequirement.created_at,
            EventEquipmentRequirement.id,
        )
    )
    return [(requirement, event) for requirement, event in db.execute(statement).tuples()]
