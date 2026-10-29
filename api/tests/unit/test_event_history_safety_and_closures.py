"""SCRUM-120: safety decisions and venue closures in the event history. Pure readers.

Safety decision entries are shown only to a viewer who may read safety decisions
elsewhere, never to the owning Organiser (ADR-0069).
"""

import uuid
from dataclasses import replace
from typing import Any

import pytest

from domain.event_history import (
    ClosureImpactRecord,
    HistoryAction,
    HistoryOutcome,
    HistorySource,
    Person,
    ReplanRecord,
    SafetyDecisionRecord,
    closure_impact_entry,
    safety_decision_entry,
    timeline,
    visible,
)
from domain.event_replanning import ReplanCause
from domain.safety_review import SafetyDecision
from tests.unit.test_event_history import STAFF, actions, at, booking, request

OFFICER = Person(uuid.uuid4(), "officer@example.com")


def decision(**overrides: Any) -> SafetyDecisionRecord:
    """The Safety Officer approving at 15h."""
    record = SafetyDecisionRecord(
        uuid.uuid4(), SafetyDecision.APPROVE, "Egress is clear", OFFICER, at(15)
    )
    return replace(record, **overrides)


def impact(**overrides: Any) -> ClosureImpactRecord:
    """Venue Staff closing Hall A over one of this event's arrangements at 25h."""
    record = ClosureImpactRecord(
        id=uuid.uuid4(),
        venue_name="Hall A",
        recorded_by=STAFF,
        recorded_at=at(25),
        starts_at=at(99),
        ends_at=at(103),
        reason="Burst pipe",
        affected_booking_ids=(uuid.uuid4(),),
    )
    return replace(record, **overrides)


# ------------------------------------------------------------ AC2 safety decisions


@pytest.mark.story("SCRUM-120")
@pytest.mark.parametrize(
    ("made", "outcome"),
    [
        (SafetyDecision.APPROVE, HistoryOutcome.APPROVED),
        (SafetyDecision.REJECT, HistoryOutcome.REJECTED),
        (SafetyDecision.REQUEST_CHANGES, HistoryOutcome.CHANGES_REQUESTED),
    ],
)
def test_a_safety_decision_shows_the_officer_time_outcome_and_comment(
    made: SafetyDecision, outcome: HistoryOutcome
) -> None:
    entry = safety_decision_entry(decision(decision=made))

    assert (entry.action, entry.actor, entry.occurred_at) == (
        HistoryAction.SAFETY_DECIDED,
        OFFICER,
        at(15),
    )
    assert (entry.outcome, entry.reason) == (outcome, "Egress is clear")
    assert entry.source_type is HistorySource.SAFETY_REVIEW
    assert entry.changes == ()


@pytest.mark.story("SCRUM-120")
def test_safety_decisions_are_left_out_entirely_for_a_viewer_who_may_not_read_them() -> None:
    """ADR-0036's rule for notes, applied to decisions: no entry, no comment, no id."""
    approval = decision()
    back = ReplanRecord(approval.id, at(20), ReplanCause.CHANGE_REQUEST)

    for_owner = timeline(request(), [], [], [], True, safety_decisions=[approval], replans=[back])
    for_staff = timeline(
        request(),
        [],
        [],
        [],
        True,
        safety_decisions=[approval],
        replans=[back],
        may_read_safety_reviews=True,
    )

    assert HistoryAction.SAFETY_DECIDED not in actions(for_owner)
    assert "Egress is clear" not in str(for_owner)
    # A return to planning is not a decision, so it stays for everyone.
    assert HistoryAction.RETURNED_TO_PLANNING in actions(for_owner)
    assert HistoryAction.SAFETY_DECIDED in actions(for_staff)


@pytest.mark.story("SCRUM-120")
def test_visible_hides_safety_decisions_unless_allowed_and_leaves_the_rest() -> None:
    entries = [safety_decision_entry(decision()), closure_impact_entry(impact())]

    assert visible(entries, True, may_read_safety_reviews=True) == entries
    assert actions(visible(entries, True)) == [HistoryAction.VENUE_CLOSED]


# ----------------------------------------------------------------- AC4 closures


@pytest.mark.story("SCRUM-120")
def test_a_closure_shows_who_when_the_period_reason_and_affected_arrangements() -> None:
    record = impact()

    entry = closure_impact_entry(record)

    assert (entry.action, entry.actor, entry.occurred_at) == (
        HistoryAction.VENUE_CLOSED,
        STAFF,
        at(25),
    )
    assert (entry.venue_name, entry.reason) == ("Hall A", "Burst pipe")
    assert (entry.period_start_at, entry.period_end_at) == (at(99), at(103))
    assert entry.affected_booking_ids == record.affected_booking_ids
    assert entry.source_type is HistorySource.VENUE_CLOSURE_IMPACT
    assert entry.changes == ()


@pytest.mark.story("SCRUM-120")
def test_a_closure_return_takes_the_staff_member_and_links_the_closure_entry() -> None:
    closure = impact()
    back = ReplanRecord(uuid.uuid4(), at(25), ReplanCause.VENUE_CLOSURE)

    entries = timeline(
        request(), [], [], [booking()], True, replans=[back], closure_impacts=[closure]
    )

    [entry] = [e for e in entries if e.action is HistoryAction.RETURNED_TO_PLANNING]
    assert (entry.actor, entry.actor_recorded) == (STAFF, True)
    assert entry.related_entry_ids == (f"venue_closed:{closure.id}",)
    assert entry.related_entry_ids[0] in {e.key for e in entries}


@pytest.mark.story("SCRUM-120")
def test_two_closures_saved_at_the_same_time_leave_the_actor_not_recorded() -> None:
    back = ReplanRecord(uuid.uuid4(), at(25), ReplanCause.VENUE_CLOSURE)

    entries = timeline(
        request(), [], [], [], True, replans=[back], closure_impacts=[impact(), impact()]
    )

    [entry] = [e for e in entries if e.action is HistoryAction.RETURNED_TO_PLANNING]
    assert (entry.actor, entry.actor_recorded, entry.related_entry_ids) == (None, False, ())


# ------------------------------------------------------------------------ ordering


@pytest.mark.story("SCRUM-120")
def test_safety_and_closure_actions_are_appended_without_moving_any_earlier_one() -> None:
    order = list(HistoryAction)

    assert order.index(HistoryAction.CLOSURE_CORRECTED) == 27
    assert order[28:] == [HistoryAction.SAFETY_DECIDED, HistoryAction.VENUE_CLOSED]
