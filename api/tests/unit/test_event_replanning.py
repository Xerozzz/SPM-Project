"""SCRUM-130: the pure rules for returning a Confirmed event to planning."""

import pytest

from domain.event_confirmation import (
    ConfirmationBlocker,
    SafetyStanding,
    problems,
)
from domain.event_replanning import ReplanCause, approval_to_invalidate, needs_replanning
from domain.event_status import EventStatus
from domain.safety_review import SafetyDecision, fingerprint
from tests.unit.test_safety_review import plan


@pytest.mark.story("SCRUM-130")
def test_only_a_confirmed_event_goes_back_to_planning() -> None:
    assert needs_replanning(EventStatus.CONFIRMED)
    for status in EventStatus:
        if status is not EventStatus.CONFIRMED:
            assert not needs_replanning(status)


@pytest.mark.story("SCRUM-130")
def test_only_a_standing_approval_is_invalidated() -> None:
    assert approval_to_invalidate(SafetyDecision.APPROVE, invalidated=False)
    assert not approval_to_invalidate(SafetyDecision.APPROVE, invalidated=True)
    assert not approval_to_invalidate(SafetyDecision.REJECT, invalidated=False)
    assert not approval_to_invalidate(SafetyDecision.REQUEST_CHANGES, invalidated=False)
    assert not approval_to_invalidate(None, invalidated=False)


@pytest.mark.story("SCRUM-130")
def test_an_invalidated_approval_cannot_confirm_even_for_the_same_plan() -> None:
    """A session change leaves the fingerprint as it was, so the marker is what blocks."""
    current = plan()
    standing = SafetyStanding(SafetyDecision.APPROVE, fingerprint(current), invalidated=True)

    found = problems(EventStatus.APPROVED, current, standing)

    assert found.safety == (ConfirmationBlocker.SAFETY_APPROVAL_STALE,)


@pytest.mark.story("SCRUM-130")
def test_the_causes_are_stored_as_short_text() -> None:
    assert [cause.value for cause in ReplanCause] == ["change_request", "venue_closure"]
