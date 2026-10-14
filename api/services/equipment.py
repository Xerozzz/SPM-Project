"""Equipment catalogue orchestration for SCRUM-84."""

import uuid

from core.database import Session
from domain.equipment import EquipmentFields, validate_equipment
from domain.validation import FieldProblem
from models.equipment import Equipment
from repositories import equipment as repo


class EquipmentError(Exception):
    """Base class for failures that the equipment router serialises."""


class DuplicateEquipmentError(EquipmentError):
    """An entry with this equipment type and location already exists."""


class InvalidEquipmentError(EquipmentError):
    """The entry has missing or invalid values."""

    def __init__(self, problems: list[FieldProblem]) -> None:
        super().__init__("the equipment entry is not valid")
        self.problems = problems


class EquipmentNotFoundError(EquipmentError):
    """The requested catalogue entry does not exist."""


def list_all(db: Session) -> list[Equipment]:
    return repo.list_active(db)


def list_distinct_types(db: Session) -> list[str]:
    """Equipment types organisers may request from the active catalogue."""
    return repo.list_distinct_active_types(db)


def deactivate(db: Session, equipment_id: uuid.UUID) -> Equipment:
    """Remove an entry from new-work catalogues without deleting its history."""
    equipment = repo.get(db, equipment_id)
    if equipment is None:
        raise EquipmentNotFoundError
    equipment.is_active = False
    return repo.save(db, equipment)


def create(db: Session, fields: EquipmentFields) -> Equipment:
    """Validate, de-duplicate, and persist one equipment catalogue entry."""
    problems = validate_equipment(fields)
    if problems:
        raise InvalidEquipmentError(problems)

    assert fields.equipment_type is not None
    assert fields.location is not None
    if repo.get_by_type_and_location(db, fields.equipment_type, fields.location) is not None:
        raise DuplicateEquipmentError

    equipment = Equipment(**_stored_values(fields))
    try:
        return repo.save(db, equipment)
    except repo.DuplicateEquipmentConstraintError as exc:
        # The preflight check gives a useful response; the database constraint makes the
        # same rule hold if two requests pass that check at the same time.
        raise DuplicateEquipmentError from exc


def update(db: Session, equipment_id: uuid.UUID, fields: EquipmentFields) -> Equipment:
    """Validate and persist an edit without replacing the catalogue record."""
    problems = validate_equipment(fields)
    if problems:
        raise InvalidEquipmentError(problems)

    equipment = repo.get(db, equipment_id)
    if equipment is None:
        raise EquipmentNotFoundError

    assert fields.equipment_type is not None
    assert fields.location is not None
    matching_entry = repo.get_by_type_and_location(db, fields.equipment_type, fields.location)
    if matching_entry is not None and matching_entry.id != equipment.id:
        raise DuplicateEquipmentError

    for field, value in _stored_values(fields).items():
        setattr(equipment, field, value)
    try:
        return repo.save(db, equipment)
    except repo.DuplicateEquipmentConstraintError as exc:
        # The database remains the final guard if a competing update wins the same identity.
        raise DuplicateEquipmentError from exc


def _stored_values(fields: EquipmentFields) -> dict[str, object]:
    """Normalise free text before it becomes the catalogue's canonical value."""
    return {
        "equipment_type": fields.equipment_type.strip() if fields.equipment_type else "",
        "description": fields.description.strip()
        if fields.description and fields.description.strip()
        else None,
        "total_quantity": fields.total_quantity,
        "location": fields.location.strip() if fields.location else "",
        "operational_status": fields.operational_status.strip()
        if fields.operational_status
        else "",
    }
