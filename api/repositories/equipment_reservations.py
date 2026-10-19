"""Equipment reservation persistence (SCRUM-53).

What *other* events hold is `repositories.equipment.reserved_quantity`, which SCRUM-52's
availability check already calls; this module answers what one event or requirement holds.
"""

import uuid
from collections.abc import Collection
from datetime import datetime

from sqlalchemy import ColumnElement, func, select, update
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


def live_totals(
    db: Session, requirement_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, bool]]:
    """AC6: for each requirement, how much it holds and whether any of that is flagged.

    One query for a whole list. A requirement with nothing live is absent from the result.
    """
    statement = (
        select(
            EquipmentReservation.requirement_id,
            func.sum(EquipmentReservation.quantity),
            func.bool_or(EquipmentReservation.flagged_at.is_not(None)),
        )
        .where(
            EquipmentReservation.released_at.is_(None),
            EquipmentReservation.requirement_id.in_(requirement_ids),
        )
        .group_by(EquipmentReservation.requirement_id)
        .order_by(EquipmentReservation.requirement_id)
    )
    return {
        requirement_id: (int(total), bool(flagged))
        for requirement_id, total, flagged in db.execute(statement).tuples()
    }


def flag_live(db: Session, requirement_id: uuid.UUID, now: datetime) -> None:
    """ADR-0033 AC6: mark a changed requirement's live reservations, without committing.

    The caller's save commits this with the change, so a change that fails flags nothing.
    A reservation flagged earlier keeps its first time, which is when it first stopped
    matching what was asked for. Released ones are left alone: they hold nothing.
    """
    db.execute(
        update(EquipmentReservation)
        .where(
            EquipmentReservation.requirement_id == requirement_id,
            EquipmentReservation.released_at.is_(None),
            EquipmentReservation.flagged_at.is_(None),
        )
        .values(flagged_at=now)
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
