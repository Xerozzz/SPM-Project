"""SCRUM-84: equipment catalogue validation stays pure and exhaustive."""

import pytest

from domain.equipment import EquipmentFields, validate_equipment


@pytest.mark.story("SCRUM-84")
def test_valid_equipment_has_no_problems() -> None:
    assert validate_equipment(EquipmentFields("Projector", None, 0, "Library", "operational")) == []


@pytest.mark.story("SCRUM-84")
def test_required_equipment_fields_are_named() -> None:
    problems = validate_equipment(EquipmentFields())

    assert [(problem.field, problem.reason) for problem in problems] == [
        ("equipment_type", "is required"),
        ("location", "is required"),
        ("operational_status", "is required"),
        ("total_quantity", "is required"),
    ]


@pytest.mark.story("SCRUM-84")
def test_blank_text_and_negative_quantity_are_invalid() -> None:
    problems = validate_equipment(EquipmentFields(" ", None, -1, " ", " "))

    assert [(problem.field, problem.reason) for problem in problems] == [
        ("equipment_type", "is required"),
        ("location", "is required"),
        ("operational_status", "is required"),
        ("total_quantity", "must be zero or more"),
    ]
