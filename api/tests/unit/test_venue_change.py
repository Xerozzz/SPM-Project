"""SCRUM-118: the pure rules for cancelling a Confirmed event's arrangement as a venue
change. The SCRUM-109 rules they sit beside are in test_venue_cancellation.py."""

import pytest

from domain.event_replanning import ReplanCause
from domain.event_status import EventStatus
from domain.validation import FieldProblem
from domain.venue_cancellation import EventRefusal, event_refusal, venue_change_problems


@pytest.mark.story("SCRUM-118")
def test_a_venue_change_is_allowed_only_for_a_confirmed_event() -> None:
    assert event_refusal(EventStatus.CONFIRMED, venue_change=True) is None
    for status in EventStatus:
        if status is not EventStatus.CONFIRMED:
            assert event_refusal(status, venue_change=True) is EventRefusal.NOT_CONFIRMED


@pytest.mark.story("SCRUM-118")
def test_the_planning_cancellation_rule_is_unchanged_without_the_flag() -> None:
    """SCRUM-109's rule, by default: Approved allowed, Confirmed sent to the venue change."""
    assert event_refusal(EventStatus.APPROVED) is None
    assert event_refusal(EventStatus.CONFIRMED) is EventRefusal.CONFIRMED_NEEDS_VENUE_CHANGE
    assert event_refusal(EventStatus.SUBMITTED) is EventRefusal.NOT_IN_PLANNING


@pytest.mark.story("SCRUM-118")
def test_confirmation_and_a_reason_are_both_required() -> None:
    """AC1: each missing part is named, so the form can show both at once."""
    assert venue_change_problems(True, "Hall flooded") == []
    assert venue_change_problems(False, "Hall flooded") == [
        FieldProblem("confirm_venue_change", "must be confirmed")
    ]
    assert venue_change_problems(True, "   ") == [FieldProblem("reason", "is required")]
    assert venue_change_problems(False, None) == [
        FieldProblem("confirm_venue_change", "must be confirmed"),
        FieldProblem("reason", "is required"),
    ]


@pytest.mark.story("SCRUM-118")
def test_the_replan_cause_fits_the_stored_column() -> None:
    """`safety_reviews.invalidation_cause` is a String(32); no migration is needed."""
    assert len(ReplanCause.VENUE_CANCELLATION.value) <= 32
