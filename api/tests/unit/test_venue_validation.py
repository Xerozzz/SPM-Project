"""SCRUM-59 AC1/AC5: what makes a venue record valid, exhaustively and without a database.

The domain layer is pure, so every rule gets its own fast test (AGENTS.md section 4).
"""

from datetime import time
from typing import Any

import pytest

from domain.validation import FieldProblem
from domain.venue import (
    REQUIRED_TEXT_FIELDS,
    ROOM_LAYOUTS,
    VenueFields,
    field_names,
    validate_venue,
)


def complete_venue(**overrides: Any) -> VenueFields:
    """A venue that passes every rule; pass field=value to break exactly one of them."""
    values: dict[str, Any] = {
        "name": "Hall A",
        "location": "Level 2, School of Computing",
        "maximum_capacity": 200,
        "facilities": ["Projector", "Hearing loop"],
        "supported_layouts": ["theatre", "classroom"],
        "accessibility_features": ["Step-free access"],
        "opens_at": time(8, 0),
        "closes_at": time(22, 0),
    }
    values.update(overrides)
    return VenueFields(**values)


def problem_fields(problems: list[FieldProblem]) -> list[str]:
    return [problem.field for problem in problems]


# ------------------------------------------------------------------ positive


@pytest.mark.story("SCRUM-59")
def test_a_complete_venue_has_no_problems() -> None:
    assert validate_venue(complete_venue()) == []


@pytest.mark.story("SCRUM-59")
def test_the_optional_lists_may_be_empty() -> None:
    # A plain room with no special facilities is still a valid venue; only the layouts it
    # supports are required, because a venue nobody can lay out cannot host anything.
    venue = complete_venue(facilities=[], accessibility_features=[])

    assert validate_venue(venue) == []


@pytest.mark.story("SCRUM-59")
@pytest.mark.parametrize("layout", ROOM_LAYOUTS)
def test_every_catalogue_layout_is_accepted(layout: str) -> None:
    assert validate_venue(complete_venue(supported_layouts=[layout])) == []


# ------------------------------------------------------------------ negative


@pytest.mark.story("SCRUM-59")
@pytest.mark.parametrize("field", REQUIRED_TEXT_FIELDS)
def test_each_missing_text_field_is_named(field: str) -> None:
    missing: dict[str, Any] = {field: None}

    assert problem_fields(validate_venue(complete_venue(**missing))) == [field]


@pytest.mark.story("SCRUM-59")
@pytest.mark.parametrize("field", REQUIRED_TEXT_FIELDS)
def test_whitespace_only_text_counts_as_missing(field: str) -> None:
    blank: dict[str, Any] = {field: "   "}

    assert problem_fields(validate_venue(complete_venue(**blank))) == [field]


@pytest.mark.story("SCRUM-59")
def test_a_missing_capacity_is_named() -> None:
    problems = validate_venue(complete_venue(maximum_capacity=None))

    assert problems == [FieldProblem("maximum_capacity", "is required")]


@pytest.mark.story("SCRUM-59")
def test_a_venue_with_no_layouts_is_refused() -> None:
    assert problem_fields(validate_venue(complete_venue(supported_layouts=[]))) == [
        "supported_layouts"
    ]


@pytest.mark.story("SCRUM-59")
def test_a_layout_outside_the_catalogue_is_refused() -> None:
    problems = validate_venue(complete_venue(supported_layouts=["cabaret"]))

    assert problem_fields(problems) == ["supported_layouts"]
    # The message lists the options, so Venue Staff can fix it without reading the code.
    assert "theatre" in problems[0].reason


@pytest.mark.story("SCRUM-59")
@pytest.mark.parametrize("field", ["opens_at", "closes_at"])
def test_each_missing_operating_hour_is_named(field: str) -> None:
    missing: dict[str, Any] = {field: None}

    assert field in problem_fields(validate_venue(complete_venue(**missing)))


@pytest.mark.story("SCRUM-59")
def test_closing_before_opening_is_refused() -> None:
    problems = validate_venue(complete_venue(opens_at=time(18, 0), closes_at=time(9, 0)))

    assert problem_fields(problems) == ["closes_at"]


@pytest.mark.story("SCRUM-59")
def test_a_missing_opening_time_does_not_also_blame_the_closing_time() -> None:
    # Only opens_at is wrong; closes_at cannot be meaningfully compared against nothing.
    problems = validate_venue(complete_venue(opens_at=None))

    assert problem_fields(problems) == ["opens_at"]


@pytest.mark.story("SCRUM-59")
def test_every_problem_is_reported_at_once() -> None:
    # AC5 names the affected field: Venue Staff see all of them in one go, not one per save.
    problems = validate_venue(VenueFields())

    assert problem_fields(problems) == [
        *REQUIRED_TEXT_FIELDS,
        "maximum_capacity",
        "supported_layouts",
        "opens_at",
        "closes_at",
    ]


# ------------------------------------------------------------------ boundary


@pytest.mark.story("SCRUM-59")
@pytest.mark.parametrize(
    ("capacity", "expected"),
    [(0, ["maximum_capacity"]), (1, []), (2, [])],
)
def test_capacity_boundary_is_one(capacity: int, expected: list[str]) -> None:
    # Just below, exactly at, and just above the smallest capacity a real venue can have.
    problems = validate_venue(complete_venue(maximum_capacity=capacity))

    assert problem_fields(problems) == expected


@pytest.mark.story("SCRUM-59")
def test_a_negative_capacity_is_refused() -> None:
    assert problem_fields(validate_venue(complete_venue(maximum_capacity=-5))) == [
        "maximum_capacity"
    ]


@pytest.mark.story("SCRUM-59")
@pytest.mark.parametrize(
    ("closes_at", "expected"),
    [(time(7, 59), ["closes_at"]), (time(8, 0), ["closes_at"]), (time(8, 1), [])],
)
def test_closing_time_boundary_is_just_after_opening(closes_at: time, expected: list[str]) -> None:
    # Opens at 08:00: closing just before, exactly at, and just after that instant.
    problems = validate_venue(complete_venue(opens_at=time(8, 0), closes_at=closes_at))

    assert problem_fields(problems) == expected


@pytest.mark.story("SCRUM-59")
def test_field_names_cover_the_whole_ticket_in_order() -> None:
    assert field_names() == (
        "name",
        "location",
        "maximum_capacity",
        "facilities",
        "supported_layouts",
        "accessibility_features",
        "opens_at",
        "closes_at",
    )
