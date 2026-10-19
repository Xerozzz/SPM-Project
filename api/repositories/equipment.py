"""Database access for equipment catalogue entries (SCRUM-84) and what is reserved (SCRUM-53)."""

import uuid
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.equipment import Equipment
from models.equipment_reservation import EquipmentReservation


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
    """SCRUM-52 AC2, SCRUM-53 AC5: how many of this type other events hold over this window.

    Sums live (unreleased) reservations whose window overlaps [start_at, end_at) by the
    half-open rule in `domain.venue_search.intervals_overlap`, so back-to-back events do
    not overlap. `excluding_event_id` is left out so an event is never short of equipment
    it holds itself.
    """
    statement = select(func.coalesce(func.sum(EquipmentReservation.quantity), 0)).where(
        EquipmentReservation.equipment_type == equipment_type,
        EquipmentReservation.released_at.is_(None),
        EquipmentReservation.event_request_id != excluding_event_id,
        EquipmentReservation.starts_at < end_at,
        EquipmentReservation.ends_at > start_at,
    )
    return int(db.scalar(statement) or 0)


def lock_entries_of_type(db: Session, equipment_type: str) -> list[Equipment]:
    """SCRUM-53: every entry of one type, row-locked until the transaction ends.

    Taken before counting what is free, so two reservations of the same type queue
    behind each other rather than both reading the same free quantity (ADR-0038). A
    catalogue edit to the type waits too, so stock cannot change under a reservation.
    Ordered by id so every caller locks in the same order and none deadlock.
    """
    statement = (
        select(Equipment)
        .where(Equipment.equipment_type == equipment_type)
        .order_by(Equipment.id)
        .with_for_update()
    )
    return list(db.scalars(statement))


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
