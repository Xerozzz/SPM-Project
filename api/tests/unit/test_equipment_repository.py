"""SCRUM-84: equipment repository constraint translation."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.equipment import Equipment
from repositories import equipment as equipment_repo


class ConstraintViolation(Exception):
    """Minimal PostgreSQL error shape used to test named-constraint translation."""

    def __init__(self, constraint_name: str | None) -> None:
        super().__init__("constraint violation")
        self.diag = SimpleNamespace(constraint_name=constraint_name)


def _integrity_error(constraint_name: str | None) -> IntegrityError:
    return IntegrityError("INSERT INTO equipment", {}, ConstraintViolation(constraint_name))


@pytest.mark.story("SCRUM-84")
def test_named_equipment_identity_constraint_becomes_duplicate_error() -> None:
    db = MagicMock(spec=Session)
    db.commit.side_effect = _integrity_error("uq_equipment_type_location")

    with pytest.raises(equipment_repo.DuplicateEquipmentConstraintError):
        equipment_repo.save(cast(Session, db), Equipment())

    db.rollback.assert_called_once()


@pytest.mark.story("SCRUM-84")
def test_other_integrity_errors_are_not_misreported_as_duplicates() -> None:
    error = _integrity_error("equipment_total_quantity_non_negative")
    db = MagicMock(spec=Session)
    db.commit.side_effect = error

    with pytest.raises(IntegrityError) as raised:
        equipment_repo.save(cast(Session, db), Equipment())

    assert raised.value is error
    db.rollback.assert_called_once()
