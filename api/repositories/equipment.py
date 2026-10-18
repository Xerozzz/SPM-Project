"""Database access for equipment catalogue entries (SCRUM-84)."""

import uuid
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.equipment import Equipment


class DuplicateEquipmentConstraintError(Exception):
    """The catalogue's type-and-location constraint rejected a concurrent insert."""


def get_by_type_and_location(db: Session, equipment_type: str, location: str) -> Equipment | None:
    """Return the entry at this type-and-location combination, if one exists."""
    statement = select(Equipment).where(
        Equipment.equipment_type == equipment_type.strip(), Equipment.location == location.strip()
    )
    return db.scalars(statement).first()


def get(db: Session, equipment_id: uuid.UUID) -> Equipment | None:
    """Return one catalogue entry by its stable identifier."""
    return db.get(Equipment, equipment_id)


def list_active(db: Session) -> list[Equipment]:
    """Return entries that Technical Support can offer for new work."""
    statement = (
        select(Equipment)
        .where(Equipment.is_active.is_(True))
        .order_by(Equipment.equipment_type, Equipment.location)
    )
    return list(db.scalars(statement))


def list_distinct_active_types(db: Session) -> list[str]:
    """Return types with at least one active entry, once each, for new requirements."""
    statement = (
        select(Equipment.equipment_type)
        .where(Equipment.is_active.is_(True))
        .distinct()
        .order_by(Equipment.equipment_type)
    )
    return list(db.scalars(statement))


def list_by_types(db: Session, equipment_types: Iterable[str]) -> list[Equipment]:
    """SCRUM-52: every entry of these types, including retired and damaged ones.

    Nothing is filtered here: which entries count toward stock is
    `domain.equipment_availability`'s rule, so it is decided and tested in one place.
    """
    statement = (
        select(Equipment)
        .where(Equipment.equipment_type.in_(list(equipment_types)))
        .order_by(Equipment.equipment_type, Equipment.id)
    )
    return list(db.scalars(statement))


def reserved_quantity(
    db: Session,
    equipment_type: str,
    start_at: datetime,
    end_at: datetime,
    excluding_event_id: uuid.UUID,
) -> int:
    """SCRUM-52 AC2: how many of this type other events have reserved over this window.

    Always 0 for now, because nothing creates reservations yet. SCRUM-53 will replace this
    body with a real query at this same call site, so the service does not change. It will
    count a reservation when its window overlaps [start_at, end_at) by the half-open rule in
    `domain.venue_search.intervals_overlap` (back-to-back events do not overlap), and leave
    out `excluding_event_id` so an event is never short of equipment it holds itself.
    """
    # Named so the signature is already the one SCRUM-53 fills in; unused until then.
    del db, equipment_type, start_at, end_at, excluding_event_id
    return 0


def save(db: Session, equipment: Equipment) -> Equipment:
    """Commit an added or edited entry and refresh its persisted values."""
    db.add(equipment)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if _violates_equipment_identity(exc):
            raise DuplicateEquipmentConstraintError from exc
        raise
    db.refresh(equipment)
    return equipment


def _violates_equipment_identity(error: IntegrityError) -> bool:
    """Return whether Postgres named the catalogue identity constraint in this error."""
    diagnostics = getattr(error.orig, "diag", None)
    return getattr(diagnostics, "constraint_name", None) == "uq_equipment_type_location"
