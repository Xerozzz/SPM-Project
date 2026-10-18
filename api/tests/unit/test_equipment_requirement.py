"""SCRUM-43 AC3, AC4 and AC5: what makes an equipment requirement valid, without a database.

The domain is pure, so every rule gets its own fast test (AGENTS.md section 4). The
catalogue and the event's existing types are passed in, so these tests say what the rules
are without saying where the data comes from.
"""

from typing import Any

import pytest

from domain.equipment_requirement import (
    MAX_TECHNICAL_REQUIREMENTS,
    RequirementFields,
    RequirementReview,
    ReviewRefusal,
    review_after_change,
    review_refusal,
    validate_change,
    validate_new_requirement,
)
from domain.event_status import EventStatus
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
    assert validate_new_requirement(complete(), _CATALOGUE, _NOTHING_YET) == []


@pytest.mark.story("SCRUM-43")
@pytest.mark.parametrize("missing", [None, "", "   "])
def test_the_equipment_type_is_required(missing: str | None) -> None:
    problems = validate_new_requirement(complete(equipment_type=missing), _CATALOGUE, _NOTHING_YET)

    assert fields_blamed(problems) == ["equipment_type"]


@pytest.mark.story("SCRUM-43")
def test_a_type_outside_the_catalogue_is_refused() -> None:
    # AC3: the catalogue is the vocabulary. A deactivated type is refused the same way an
    # invented one is, because the service only passes the active ones in.
    problems = validate_new_requirement(
        complete(equipment_type="Smoke machine"), _CATALOGUE, _NOTHING_YET
    )

    assert fields_blamed(problems) == ["equipment_type"]
    assert problems[0].reason == "is not an active catalogue type"


@pytest.mark.story("SCRUM-43")
def test_a_type_is_matched_after_trimming() -> None:
    # The organiser's stored value and a typed one should not disagree over a space.
    assert (
        validate_new_requirement(complete(equipment_type="  Projector  "), _CATALOGUE, _NOTHING_YET)
        == []
    )


@pytest.mark.story("SCRUM-43")
@pytest.mark.parametrize(
    ("quantity", "is_problem"),
    # Literal 1, not MINIMUM_QUANTITY: naming the symbol on both sides means the test
    # agrees with whatever the constant says, so raising it to 2 went unnoticed.
    [(None, True), (0, True), (-1, True), (1, False), (2, False), (500, False)],
)
def test_the_quantity_must_be_a_positive_whole_number(
    quantity: int | None, is_problem: bool
) -> None:
    # AC3 at the boundary: below, exactly at, and above the smallest real quantity.
    problems = validate_new_requirement(complete(quantity=quantity), _CATALOGUE, _NOTHING_YET)

    assert fields_blamed(problems) == (["quantity"] if is_problem else [])


@pytest.mark.story("SCRUM-43")
def test_a_boolean_is_not_a_quantity() -> None:
    # `True` is an `int` in Python and would otherwise pass as a quantity of one.
    problems = validate_new_requirement(complete(quantity=True), _CATALOGUE, _NOTHING_YET)

    assert fields_blamed(problems) == ["quantity"]


@pytest.mark.story("SCRUM-43")
def test_technical_requirements_are_optional() -> None:
    assert (
        validate_new_requirement(complete(technical_requirements=None), _CATALOGUE, _NOTHING_YET)
        == []
    )


@pytest.mark.story("SCRUM-43")
@pytest.mark.parametrize("length", [MAX_TECHNICAL_REQUIREMENTS, MAX_TECHNICAL_REQUIREMENTS + 1])
def test_technical_requirements_have_a_limit(length: int) -> None:
    problems = validate_new_requirement(
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
    problems = validate_new_requirement(complete(), _CATALOGUE, frozenset({"Projector"}))

    assert fields_blamed(problems) == ["equipment_type"]
    assert problems[0].reason == "is already required for this event"


@pytest.mark.story("SCRUM-43")
def test_a_different_type_on_the_same_event_is_fine() -> None:
    assert (
        validate_new_requirement(
            complete(equipment_type="Microphone"), _CATALOGUE, frozenset({"Projector"})
        )
        == []
    )


@pytest.mark.story("SCRUM-43")
def test_every_problem_is_reported_at_once() -> None:
    # The same rule SCRUM-59 set for venues: all the problems in one save, not one per try.
    problems = validate_new_requirement(RequirementFields(), _CATALOGUE, _NOTHING_YET)

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


# ------------------------------------------------- changing one that already exists


@pytest.mark.story("SCRUM-43")
def test_a_change_is_judged_without_looking_at_the_equipment_type() -> None:
    """The fix for a requirement frozen by a deactivated catalogue entry.

    `validate_change` is not given the catalogue at all, so there is no way for it to
    refuse an edit because the type it already names has since been retired. Asserted by
    signature as much as by behaviour: a caller cannot pass one in.
    """
    assert validate_change(3, "Still fine") == []


@pytest.mark.story("SCRUM-43")
@pytest.mark.parametrize(
    ("quantity", "is_problem"),
    [(None, True), (0, True), (-1, True), (1, False), (9, False)],
)
def test_a_change_still_has_to_be_a_positive_whole_number(
    quantity: int | None, is_problem: bool
) -> None:
    # AC3 applies to an edit as much as to an addition: the merged record has to be valid.
    assert fields_blamed(validate_change(quantity, None)) == (["quantity"] if is_problem else [])


@pytest.mark.story("SCRUM-43")
def test_a_change_respects_the_technical_text_limit() -> None:
    too_long = "x" * (MAX_TECHNICAL_REQUIREMENTS + 1)

    assert fields_blamed(validate_change(1, too_long)) == ["technical_requirements"]


# --------------------------------------------------------------------------- SCRUM-44


@pytest.mark.story("SCRUM-44")
def test_a_live_requirement_of_an_event_in_planning_may_be_reviewed() -> None:
    assert review_refusal(EventStatus.APPROVED, removed=False) is None


@pytest.mark.story("SCRUM-44")
@pytest.mark.parametrize("status", [s for s in EventStatus if s is not EventStatus.APPROVED])
def test_a_requirement_outside_planning_may_not_be_reviewed(status: EventStatus) -> None:
    # Boundary: APPROVED is the only status that passes, on either side of it.
    assert review_refusal(status, removed=False) is ReviewRefusal.EVENT_NOT_IN_PLANNING


@pytest.mark.story("SCRUM-44")
@pytest.mark.parametrize("status", list(EventStatus))
def test_a_removed_requirement_may_not_be_reviewed_whatever_the_event_status(
    status: EventStatus,
) -> None:
    # Removal is checked first, so a removed line reads as missing rather than as a
    # conflict about its event.
    assert review_refusal(status, removed=True) is ReviewRefusal.REQUIREMENT_REMOVED
