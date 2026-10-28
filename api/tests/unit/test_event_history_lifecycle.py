"""SCRUM-120: confirmation, return to planning and cancellation in the event history.

Pure readers, no database. The return to planning has no row of its own, so its actor is
the cause's, matched by cause and exact time, or not shown at all (ADR-0067).
"""

import uuid
from dataclasses import replace
from typing import Any

import pytest

from domain.event_history import (
    HistoryAction,
    HistorySource,
    ReplanCauseRecord,
    ReplanRecord,
    cancellation_entry,
    confirmation_entry,
    replan_entry,
    timeline,
)
from domain.event_replanning import ReplanCause
from domain.venue_booking import BookingStatus
from tests.unit.test_event_history import COORDINATOR, LEAD, STAFF, actions, at, booking, request
from tests.unit.test_event_history_equipment import reservation

REASON = "Funding withdrawn"


def replan(**overrides: Any) -> ReplanRecord:
    """An approval invalidated at 20h because a change request was approved."""
    return replace(ReplanRecord(uuid.uuid4(), at(20), ReplanCause.CHANGE_REQUEST), **overrides)


def cause(**overrides: Any) -> ReplanCauseRecord:
    """The Coordinator approving a change request at 20h."""
    record = ReplanCauseRecord(ReplanCause.CHANGE_REQUEST, COORDINATOR, at(20), None)
    return replace(record, **overrides)


def cancelled_booking(**overrides: Any) -> Any:
    """An arrangement cancelled by the Coordinator at 30h with the event's reason."""
    values: dict[str, Any] = {
        "status": BookingStatus.CANCELLED,
        "cancelled_by": COORDINATOR,
        "cancelled_at": at(30),
        "cancellation_reason": REASON,
    }
    return booking(**(values | overrides))


# ------------------------------------------------------------------ AC3 confirmation


@pytest.mark.story("SCRUM-120")
def test_a_confirmation_names_the_coordinator_and_time() -> None:
    entry = confirmation_entry(request(confirmed_by=COORDINATOR, confirmed_at=at(10)))

    assert entry is not None
    assert (entry.action, entry.actor, entry.occurred_at) == (
        HistoryAction.EVENT_CONFIRMED,
        COORDINATOR,
        at(10),
    )
    assert entry.source_type is HistorySource.EVENT_REQUEST
    assert entry.changes == ()


@pytest.mark.story("SCRUM-120")
def test_an_event_never_confirmed_has_no_confirmation_entry() -> None:
    assert confirmation_entry(request()) is None


# ------------------------------------------------------------ AC3 return to planning


@pytest.mark.story("SCRUM-120")
@pytest.mark.parametrize("why", list(ReplanCause))
def test_a_return_takes_the_actor_of_the_one_cause_at_the_same_time(why: ReplanCause) -> None:
    entry = replan_entry(replan(cause=why), [cause(cause=why, actor=STAFF)])

    assert (entry.action, entry.occurred_at, entry.replan_cause) == (
        HistoryAction.RETURNED_TO_PLANNING,
        at(20),
        why,
    )
    assert (entry.actor, entry.actor_recorded) == (STAFF, True)
    assert entry.source_type is HistorySource.SAFETY_REVIEW


@pytest.mark.story("SCRUM-120")
@pytest.mark.parametrize(
    "candidates",
    [
        pytest.param([], id="no cause recorded"),
        pytest.param([cause(at=at(20.001))], id="a cause a moment later"),
        pytest.param([cause(cause=ReplanCause.VENUE_CLOSURE)], id="another cause at that time"),
        pytest.param([cause(), cause(actor=LEAD)], id="two causes at that time"),
    ],
)
def test_without_exactly_one_match_the_actor_is_not_recorded(
    candidates: list[ReplanCauseRecord],
) -> None:
    entry = replan_entry(replan(), candidates)

    assert (entry.actor, entry.actor_recorded) == (None, False)
    assert entry.related_entry_ids == ()
    assert entry.replan_cause is ReplanCause.CHANGE_REQUEST


@pytest.mark.story("SCRUM-120")
def test_a_venue_change_return_links_the_cancelled_arrangement_and_ranks_after_it() -> None:
    arrangement = cancelled_booking(cancelled_at=at(20))
    record = replan(cause=ReplanCause.VENUE_CANCELLATION)

    entries = timeline(request(), [], [], [arrangement], True, replans=[record])

    [back] = [e for e in entries if e.action is HistoryAction.RETURNED_TO_PLANNING]
    assert (back.actor, back.actor_recorded) == (COORDINATOR, True)
    assert back.related_entry_ids == (f"arrangement_cancelled:{arrangement.id}",)
    assert back.related_entry_ids[0] in {e.key for e in entries}
    assert actions(entries)[-2:] == [
        HistoryAction.ARRANGEMENT_CANCELLED,
        HistoryAction.RETURNED_TO_PLANNING,
    ]


@pytest.mark.story("SCRUM-120")
def test_a_cause_with_no_entry_of_its_own_gives_the_actor_but_no_link() -> None:
    entry = replan_entry(replan(), [cause()])

    assert (entry.actor, entry.related_entry_ids) == (COORDINATOR, ())


@pytest.mark.story("SCRUM-120")
def test_each_return_is_its_own_entry() -> None:
    first, second = replan(invalidated_at=at(20)), replan(invalidated_at=at(40))

    entries = timeline(
        request(),
        [],
        [],
        [],
        True,
        replans=[first, second],
        replan_causes=[cause(), cause(at=at(40), actor=LEAD)],
    )

    returns = [e for e in entries if e.action is HistoryAction.RETURNED_TO_PLANNING]
    assert [(e.source_id, e.actor) for e in returns] == [
        (first.id, COORDINATOR),
        (second.id, LEAD),
    ]


# ------------------------------------------------------------------ AC6 cancellation


@pytest.mark.story("SCRUM-120")
def test_a_cancellation_is_one_entry_with_its_reason_linking_what_it_released() -> None:
    record = request(cancelled_by=COORDINATOR, cancelled_at=at(30), cancellation_reason=REASON)
    arrangement = cancelled_booking()
    released = reservation(released_by=COORDINATOR, released_at=at(30))

    entries = timeline(record, [], [], [arrangement], True, reservations=[released])

    [entry] = [e for e in entries if e.action is HistoryAction.EVENT_CANCELLED]
    assert (entry.actor, entry.occurred_at, entry.reason) == (COORDINATOR, at(30), REASON)
    assert set(entry.related_entry_ids) == {
        f"arrangement_cancelled:{arrangement.id}",
        f"reservation_released:{released.id}",
    }
    # Linked, not repeated: each released item is still its own single entry.
    keys = [e.key for e in entries]
    assert set(entry.related_entry_ids) <= set(keys)
    assert len(keys) == len(set(keys))
    assert actions(entries)[-1] is HistoryAction.EVENT_CANCELLED


@pytest.mark.story("SCRUM-120")
def test_only_what_the_cancellation_itself_released_is_linked() -> None:
    record = request(cancelled_by=COORDINATOR, cancelled_at=at(30), cancellation_reason=REASON)
    earlier = cancelled_booking(cancelled_at=at(12), cancellation_reason="Moved online")
    other_actor = cancelled_booking(cancelled_by=LEAD)
    live = booking()

    entry = cancellation_entry(record, [earlier, other_actor, live], [reservation()])

    assert entry is not None
    assert entry.related_entry_ids == ()


@pytest.mark.story("SCRUM-120")
def test_an_event_never_cancelled_has_no_cancellation_entry() -> None:
    assert cancellation_entry(request(), [cancelled_booking()], []) is None


# ------------------------------------------------------------------------ ordering


@pytest.mark.story("SCRUM-120")
def test_lifecycle_actions_are_appended_without_moving_any_earlier_one() -> None:
    order = list(HistoryAction)

    assert order.index(HistoryAction.RESERVATION_RELEASED) == 20
    # Later SCRUM-120 actions append after these, so they are pinned as a slice.
    assert order[21:24] == [
        HistoryAction.EVENT_CONFIRMED,
        HistoryAction.RETURNED_TO_PLANNING,
        HistoryAction.EVENT_CANCELLED,
    ]
