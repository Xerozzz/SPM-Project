"""Equipment catalogue orchestration for SCRUM-84."""

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


def list_all(db: Session) -> list[Equipment]:
    return repo.list_all(db)


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
