"""SCRUM-36: which fields an ordinary planning update may change, and how they are checked."""

import pytest

from domain.event_request import ORDINARY_FIELDS, field_names, validate_ordinary_update


@pytest.mark.story("SCRUM-36")
def test_ordinary_fields_exclude_dates_attendance_venue_and_equipment() -> None:
    # AC3: these may only change through change control, never through this flow.
    for protected in (
        "start_at",
        "end_at",
        "expected_attendance",
        "venue_requirement",
        "equipment_requirement",
    ):
        assert protected not in ORDINARY_FIELDS
    # Every ordinary field is a real event request field, so none is a silent typo.
    assert set(ORDINARY_FIELDS) <= set(field_names())


@pytest.mark.story("SCRUM-36")
def test_a_valid_ordinary_update_has_no_problems() -> None:
    assert validate_ordinary_update({"name": "Orientation Night", "purpose": "Welcome"}) == []


@pytest.mark.story("SCRUM-36")
def test_an_empty_update_has_no_problems() -> None:
    assert validate_ordinary_update({}) == []


@pytest.mark.story("SCRUM-36")
def test_an_ordinary_field_cannot_be_blanked_or_cleared() -> None:
    problems = validate_ordinary_update({"name": "   ", "description": None, "purpose": "Ok"})

    assert [(p.field, p.reason) for p in problems] == [
        ("name", "is required"),
        ("description", "is required"),
    ]


@pytest.mark.story("SCRUM-36")
def test_fields_that_are_not_sent_are_not_checked() -> None:
    # Only what the coordinator changes is validated. An untouched field is left alone.
    assert validate_ordinary_update({"layout_requirement": "Banquet"}) == []
