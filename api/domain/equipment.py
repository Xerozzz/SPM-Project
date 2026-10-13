"""Validation rules for equipment catalogue entries (SCRUM-84)."""

from dataclasses import dataclass

from domain.validation import FieldProblem

OPERATIONAL_STATUSES: tuple[str, ...] = ("Operational", "Damaged", "Under Maintenance")
MAX_EQUIPMENT_TYPE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 1000
MAX_LOCATION_LENGTH = 200
MAX_OPERATIONAL_STATUS_LENGTH = 100


@dataclass(frozen=True)
class EquipmentFields:
    """Values supplied while a Technical Support Staff member adds equipment."""

    equipment_type: str | None = None
    description: str | None = None
    total_quantity: int | float | str | bool | None = None
    location: str | None = None
    operational_status: str | None = None


def validate_equipment(equipment: EquipmentFields) -> list[FieldProblem]:
    """Return each requirement that prevents an equipment entry being saved."""
    problems: list[FieldProblem] = []

    for field in ("equipment_type", "location", "operational_status"):
        if _is_blank(getattr(equipment, field)):
            problems.append(FieldProblem(field, "is required"))

    problems.extend(
        _text_length_problems(
            equipment,
            (
                ("equipment_type", MAX_EQUIPMENT_TYPE_LENGTH),
                ("description", MAX_DESCRIPTION_LENGTH),
                ("location", MAX_LOCATION_LENGTH),
                ("operational_status", MAX_OPERATIONAL_STATUS_LENGTH),
            ),
        )
    )

    if (
        equipment.operational_status is not None
        and equipment.operational_status.strip()
        and len(equipment.operational_status.strip()) <= MAX_OPERATIONAL_STATUS_LENGTH
        and equipment.operational_status.strip() not in OPERATIONAL_STATUSES
    ):
        problems.append(
            FieldProblem(
                "operational_status",
                f"must be one of: {', '.join(OPERATIONAL_STATUSES)}",
            )
        )

    if equipment.total_quantity is None:
        problems.append(FieldProblem("total_quantity", "is required"))
    elif not isinstance(equipment.total_quantity, int) or isinstance(
        equipment.total_quantity, bool
    ):
        problems.append(FieldProblem("total_quantity", "must be a whole number"))
    elif equipment.total_quantity < 0:
        problems.append(FieldProblem("total_quantity", "must be zero or more"))

    return problems


def _is_blank(value: str | None) -> bool:
    return value is None or not value.strip()


def _text_length_problems(
    equipment: EquipmentFields, limits: tuple[tuple[str, int], ...]
) -> list[FieldProblem]:
    """Keep values that would exceed the database columns out of persistence."""
    return [
        FieldProblem(field, f"must be {maximum} characters or fewer")
        for field, maximum in limits
        if (value := getattr(equipment, field)) is not None and len(value.strip()) > maximum
    ]
