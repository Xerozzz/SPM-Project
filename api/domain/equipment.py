"""Validation rules for equipment catalogue entries (SCRUM-84)."""

from dataclasses import dataclass

from domain.validation import FieldProblem


@dataclass(frozen=True)
class EquipmentFields:
    """Values supplied while a Technical Support Staff member adds equipment."""

    equipment_type: str | None = None
    description: str | None = None
    total_quantity: int | None = None
    location: str | None = None
    operational_status: str | None = None


def validate_equipment(equipment: EquipmentFields) -> list[FieldProblem]:
    """Return each requirement that prevents an equipment entry being saved."""
    problems: list[FieldProblem] = []

    for field in ("equipment_type", "location", "operational_status"):
        if _is_blank(getattr(equipment, field)):
            problems.append(FieldProblem(field, "is required"))

    if equipment.total_quantity is None:
        problems.append(FieldProblem("total_quantity", "is required"))
    elif equipment.total_quantity < 0:
        problems.append(FieldProblem("total_quantity", "must be zero or more"))

    return problems


def _is_blank(value: str | None) -> bool:
    return value is None or not value.strip()
