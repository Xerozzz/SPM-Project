"""SCRUM-80: when an event may be confirmed.

Pure, so every rule gets its own fast test (AGENTS.md section 4). The arrangement
throughout is the one SCRUM-79 already calls reviewable — a held venue and fully
arranged equipment — plus a safety approval of exactly that plan, which is the only
state AC2 lets a confirmation happen from. Each test breaks exactly one thing.

The arrangement half is deliberately not re-tested here. It is `domain.safety_review`'s
rule, tested there; what these tests check is that confirmation asks it at all, and what
confirmation adds on top (AC2's approval, AC7's staleness).
"""

import pytest

from domain.event_confirmation import (
    ConfirmationBlocker,
    SafetyStanding,
    may_confirm,
    problems,
)
from domain.event_status import EventStatus
from domain.safety_review import PlanSnapshot, ReviewBlocker, SafetyDecision, fingerprint
from tests.unit.test_safety_review import plan, venue


def approved_of(snapshot: PlanSnapshot | None = None) -> SafetyStanding:
    """A safety approval of the plan passed, or of the default plan."""
    return SafetyStanding(
        decision=SafetyDecision.APPROVE,
        plan_fingerprint=fingerprint(plan() if snapshot is None else snapshot),
    )


@pytest.mark.story("SCRUM-80")
def test_an_arranged_and_approved_event_may_be_confirmed() -> None:
    assert may_confirm(EventStatus.APPROVED, plan(), approved_of()) is True
    assert problems(EventStatus.APPROVED, plan(), approved_of()).reasons() == []


@pytest.mark.story("SCRUM-80")
def test_an_event_that_has_never_been_reviewed_cannot_be_confirmed() -> None:
    """AC2: the customer makes safety approval a precondition, not a formality."""
    found = problems(EventStatus.APPROVED, plan(), None)

    assert found.safety == (ConfirmationBlocker.SAFETY_NOT_REVIEWED,)
    assert may_confirm(EventStatus.APPROVED, plan(), None) is False


@pytest.mark.story("SCRUM-80")
@pytest.mark.parametrize("decision", [SafetyDecision.REJECT, SafetyDecision.REQUEST_CHANGES])
def test_a_decision_that_sent_the_plan_back_does_not_authorise_confirmation(
    decision: SafetyDecision,
) -> None:
    standing = SafetyStanding(decision=decision, plan_fingerprint=fingerprint(plan()))

    found = problems(EventStatus.APPROVED, plan(), standing)

    assert found.safety == (ConfirmationBlocker.SAFETY_NOT_APPROVED,)


@pytest.mark.story("SCRUM-80")
def test_an_approval_of_a_plan_that_has_since_changed_authorises_nothing() -> None:
    """AC7, and the reason ADR-0048 stores a fingerprint at all.

    The Officer approved two sessions. A third was added afterwards. Nobody has judged
    the event as it now stands, and the earlier approval is not a statement about it.
    """
    judged = plan()
    now_running = plan(venues=[venue(), venue(session_label="Evening session")])

    found = problems(EventStatus.APPROVED, now_running, approved_of(judged))

    assert found.safety == (ConfirmationBlocker.SAFETY_APPROVAL_STALE,)


@pytest.mark.story("SCRUM-80")
def test_a_change_that_cannot_affect_safety_leaves_the_approval_standing() -> None:
    """The flip side of AC7: the fingerprint covers what bears on safety and no more,
    so an approval is not thrown away for a change that could not alter it."""
    renamed = plan(expected_attendance=150)

    assert problems(EventStatus.APPROVED, renamed, approved_of(plan())).reasons() == []


@pytest.mark.story("SCRUM-80")
def test_the_arrangement_rule_is_asked_rather_than_restated() -> None:
    """AC2, AC3 and AC10 are SCRUM-79's question, so breaking the plan blocks here too.

    Checked through one representative break rather than every one: the vocabulary that
    comes back is `ReviewBlocker`, which means the rule really is the shared one and not
    a copy that could drift.
    """
    found = problems(EventStatus.APPROVED, plan(venues=[]), approved_of())

    assert ReviewBlocker.NO_VENUE_ARRANGEMENT in found.arrangement
    assert found.blocked is True


@pytest.mark.story("SCRUM-80")
def test_an_expired_hold_blocks_confirmation() -> None:
    """AC3 and AC8: a hold that has run out is not an arrangement to commit."""
    found = problems(EventStatus.APPROVED, plan(venues=[venue(hold_expired=True)]), approved_of())

    assert ReviewBlocker.HOLD_EXPIRED in found.arrangement


@pytest.mark.story("SCRUM-80")
@pytest.mark.parametrize(
    "status",
    [EventStatus.DRAFT, EventStatus.SUBMITTED, EventStatus.REJECTED, EventStatus.CONFIRMED],
)
def test_an_event_outside_planning_reports_only_that(status: EventStatus) -> None:
    """Including one already confirmed: re-confirming is not a thing to do twice, and
    listing arrangement work for it would invite a caller to act on the rest."""
    found = problems(status, plan(), approved_of())

    assert found.safety == (ConfirmationBlocker.NOT_IN_PLANNING,)
    assert found.arrangement == ()


@pytest.mark.story("SCRUM-80")
def test_every_reason_is_reported_at_once() -> None:
    """A Coordinator chasing three people should see all three, not one per round trip."""
    found = problems(EventStatus.APPROVED, plan(venues=[]), None)

    assert found.reasons() == [
        ReviewBlocker.NO_VENUE_ARRANGEMENT.value,
        ConfirmationBlocker.SAFETY_NOT_REVIEWED.value,
    ]


@pytest.mark.story("SCRUM-80")
def test_the_blocker_vocabulary_is_closed() -> None:
    """The screen maps every value, so a new one must be a deliberate edit on both sides."""
    assert {blocker.value for blocker in ConfirmationBlocker} == {
        "not_in_planning",
        "safety_not_reviewed",
        "safety_not_approved",
        "safety_approval_stale",
    }
