"""Equipment requirement persistence (SCRUM-43)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.equipment_requirement_change import EquipmentRequirementChange
from models.event_equipment_requirement import EventEquipmentRequirement


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


def save(db: Session, requirement: EventEquipmentRequirement) -> EventEquipmentRequirement:
    """Commit the requirement and any audit row added alongside it."""
    db.add(requirement)
    db.commit()
    db.refresh(requirement)
    return requirement


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
