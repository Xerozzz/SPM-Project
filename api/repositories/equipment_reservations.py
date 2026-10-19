"""Equipment reservation persistence (SCRUM-53).

What *other* events hold is `repositories.equipment.reserved_quantity`, which SCRUM-52's
availability check already calls; this module answers what one event or requirement holds.
"""

import uuid

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from models.equipment_reservation import EquipmentReservation


def held_by_requirement(db: Session, requirement_id: uuid.UUID) -> int:
    """How much of one requirement is reserved, across every time it was reserved."""
    return _live_sum(db, EquipmentReservation.requirement_id == requirement_id)


def held_by_event(db: Session, event_request_id: uuid.UUID, equipment_type: str) -> int:
    """How many of a type one event holds, including any held for a since-removed line.

    Removing a requirement does not release its reservation (that is Event Change
    Management's work), so this can be more than the live requirement's own share.
    """
    return _live_sum(
        db,
        EquipmentReservation.event_request_id == event_request_id,
        EquipmentReservation.equipment_type == equipment_type,
    )


def add(db: Session, reservation: EquipmentReservation) -> EquipmentReservation:
    """Commit a new reservation, which also releases the catalogue row locks."""
    db.add(reservation)
    db.commit()
    db.refresh(reservation)
    return reservation


def _live_sum(db: Session, *conditions: ColumnElement[bool]) -> int:
    statement = select(func.coalesce(func.sum(EquipmentReservation.quantity), 0)).where(
        EquipmentReservation.released_at.is_(None), *conditions
    )
    return int(db.scalar(statement) or 0)
