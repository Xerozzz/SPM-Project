"""SCRUM-43 AC3, AC4 and AC5: what makes an equipment requirement valid, without a database.

The domain is pure, so every rule gets its own fast test (AGENTS.md section 4). The
catalogue and the event's existing types are passed in, so these tests say what the rules
are without saying where the data comes from.
"""

from typing import Any

import pytest

from domain.equipment_requirement import (
    MAX_TECHNICAL_REQUIREMENTS,
    MINIMUM_QUANTITY,
    RequirementFields,
    RequirementReview,
    review_after_change,
    validate_requirement,
)
from domain.validation import FieldProblem

_CATALOGUE = frozenset({"Projector", "Microphone"})
_NOTHING_YET: frozenset[str] = frozenset()


def complete(**overrides: Any) -> RequirementFields:
    """A requirement that passes every rule; pass field=value to break exactly one."""
    values: dict[str, Any] = {
        "equipment_type": "Projector",
        "quantity": 2,
        "technical_requirements": "Needs an HDMI cable",
    }
    values.update(overrides)
    return RequirementFields(**values)


def fields_blamed(problems: list[FieldProblem]) -> list[str]:
    return [problem.field for problem in problems]


# --------------------------------------------------------------------------- AC3


@pytest.mark.story("SCRUM-43")
def test_a_complete_requirement_is_valid() -> None:
    assert validate_requirement(complete(), _CATALOGUE, _NOTHING_YET) == []


@pytest.mark.story("SCRUM-43")
@pytest.mark.parametrize("missing", [None, "", "   "])
def test_the_equipment_type_is_required(missing: str | None) -> None:
    problems = validate_requirement(complete(equipment_type=missing), _CATALOGUE, _NOTHING_YET)

    assert fields_blamed(problems) == ["equipment_type"]


@pytest.mark.story("SCRUM-43")
def test_a_type_outside_the_catalogue_is_refused() -> None:
    # AC3: the catalogue is the vocabulary. A deactivated type is refused the same way an
    # invented one is, because the service only passes the active ones in.
    problems = validate_requirement(
        complete(equipment_type="Smoke machine"), _CATALOGUE, _NOTHING_YET
    )

    assert fields_blamed(problems) == ["equipment_type"]
    assert problems[0].reason == "is not an active catalogue type"


@pytest.mark.story("SCRUM-43")
def test_a_type_is_matched_after_trimming() -> None:
    # The organiser's stored value and a typed one should not disagree over a space.
    assert (
        validate_requirement(complete(equipment_type="  Projector  "), _CATALOGUE, _NOTHING_YET)
        == []
    )


@pytest.mark.story("SCRUM-43")
@pytest.mark.parametrize(
    ("quantity", "is_problem"),
    [(None, True), (0, True), (-1, True), (MINIMUM_QUANTITY, False), (2, False), (500, False)],
)
def test_the_quantity_must_be_a_positive_whole_number(
    quantity: int | None, is_problem: bool
) -> None:
    # AC3 at the boundary: below, exactly at, and above the smallest real quantity.
    problems = validate_requirement(complete(quantity=quantity), _CATALOGUE, _NOTHING_YET)

    assert fields_blamed(problems) == (["quantity"] if is_problem else [])


@pytest.mark.story("SCRUM-43")
def test_a_boolean_is_not_a_quantity() -> None:
    # `True` is an `int` in Python and would otherwise pass as a quantity of one.
    problems = validate_requirement(complete(quantity=True), _CATALOGUE, _NOTHING_YET)

    assert fields_blamed(problems) == ["quantity"]


@pytest.mark.story("SCRUM-43")
def test_technical_requirements_are_optional() -> None:
    assert (
        validate_requirement(complete(technical_requirements=None), _CATALOGUE, _NOTHING_YET) == []
    )


@pytest.mark.story("SCRUM-43")
@pytest.mark.parametrize("length", [MAX_TECHNICAL_REQUIREMENTS, MAX_TECHNICAL_REQUIREMENTS + 1])
def test_technical_requirements_have_a_limit(length: int) -> None:
    problems = validate_requirement(
        complete(technical_requirements="x" * length), _CATALOGUE, _NOTHING_YET
    )

    assert fields_blamed(problems) == (
        [] if length == MAX_TECHNICAL_REQUIREMENTS else ["technical_requirements"]
    )


# --------------------------------------------------------------------------- AC4


@pytest.mark.story("SCRUM-43")
def test_the_same_type_twice_on_one_event_is_refused() -> None:
    # AC4: a second line for the same thing is an edit, not an addition. Two lines would
    # leave two answers to "how many do we need".
    problems = validate_requirement(complete(), _CATALOGUE, frozenset({"Projector"}))

    assert fields_blamed(problems) == ["equipment_type"]
    assert problems[0].reason == "is already required for this event"


@pytest.mark.story("SCRUM-43")
def test_a_different_type_on_the_same_event_is_fine() -> None:
    assert (
        validate_requirement(
            complete(equipment_type="Microphone"), _CATALOGUE, frozenset({"Projector"})
        )
        == []
    )


@pytest.mark.story("SCRUM-43")
def test_editing_a_requirement_does_not_collide_with_itself() -> None:
    # The service leaves the requirement being edited out of the set it passes, so keeping
    # its own type is not a duplicate.
    assert validate_requirement(complete(), _CATALOGUE, _NOTHING_YET) == []


@pytest.mark.story("SCRUM-43")
def test_every_problem_is_reported_at_once() -> None:
    # The same rule SCRUM-59 set for venues: all the problems in one save, not one per try.
    problems = validate_requirement(RequirementFields(), _CATALOGUE, _NOTHING_YET)

    assert fields_blamed(problems) == ["equipment_type", "quantity"]


# --------------------------------------------------------------------------- AC5


@pytest.mark.story("SCRUM-43")
def test_a_change_sends_the_requirement_back_for_review() -> None:
    # AC5: whatever Technical Support Staff last said is about a requirement that no longer
    # exists in that form, so it cannot stand (SCRUM-44).
    assert review_after_change() is RequirementReview.PENDING_REVIEW


@pytest.mark.story("SCRUM-43")
def test_the_review_vocabulary_is_the_one_scrum_44_records() -> None:
    # Written down once so SCRUM-44 extends this list rather than inventing a second one.
    assert {review.value for review in RequirementReview} == {
        "pending_review",
        "available",
        "partially_available",
        "unavailable",
    }
