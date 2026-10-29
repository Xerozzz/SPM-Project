"""SCRUM-136: hold expiry changes in the event history. Pure readers, no database."""

import uuid
from dataclasses import replace
from typing import Any

import pytest

from domain.event_history import (
    FieldChange,
    FieldKind,
    HistoryAction,
    HistorySource,
    HoldExpiryChangeRecord,
    hold_expiry_change_entry,
    timeline,
)
from tests.unit.test_event_history import STAFF, actions, at, request
from tests.unit.test_event_history_venue_changes import held


def change(**overrides: Any) -> HoldExpiryChangeRecord:
    """Venue Staff moving Hall A's hold from 30h to 40h, at 8h."""
    record = HoldExpiryChangeRecord(
        id=uuid.uuid4(),
        venue_name="Hall A",
        session_label="Main session",
        session_start_at=at(100),
        session_end_at=at(102),
        old_expires_at=at(30),
        new_expires_at=at(40),
        changed_by=STAFF,
        changed_at=at(8),
    )
    return replace(record, **overrides)


# ------------------------------------------------------------ AC2 one entry per change


@pytest.mark.story("SCRUM-136")
def test_an_expiry_change_shows_the_staff_member_time_hold_and_both_expiries() -> None:
    record = change()

    entry = hold_expiry_change_entry(record)

    assert (entry.action, entry.actor, entry.occurred_at) == (
        HistoryAction.HOLD_EXPIRY_CHANGED,
        STAFF,
        at(8),
    )
    assert (entry.source_type, entry.source_id) == (
        HistorySource.VENUE_HOLD_EXPIRY_CHANGE,
        record.id,
    )
    assert (entry.venue_name, entry.session_label) == ("Hall A", "Main session")
    assert (entry.session_start_at, entry.session_end_at) == (at(100), at(102))
    assert entry.changes == (
        FieldChange(
            "expires_at", "Held until", at(30).isoformat(), at(40).isoformat(), FieldKind.DATETIME
        ),
    )


@pytest.mark.story("SCRUM-136")
def test_the_expiry_reader_emits_exactly_its_whitelisted_field() -> None:
    """ADR-0064 rule 1: adding a field to `changes` must be a deliberate edit here."""
    entry = hold_expiry_change_entry(change())

    assert {c.field for c in entry.changes} == {"expires_at"}
    assert all(c.label and c.kind is FieldKind.DATETIME for c in entry.changes)


@pytest.mark.story("SCRUM-136")
def test_a_shortened_hold_shows_the_later_expiry_as_old() -> None:
    entry = hold_expiry_change_entry(change(old_expires_at=at(40), new_expires_at=at(20)))

    [shortened] = entry.changes
    assert (shortened.old, shortened.new) == (at(40).isoformat(), at(20).isoformat())


# ----------------------------------------------------------------------- AC3 order


@pytest.mark.story("SCRUM-136")
def test_several_changes_to_one_hold_appear_in_the_order_made() -> None:
    first = change(changed_at=at(8), old_expires_at=at(30), new_expires_at=at(40))
    second = change(changed_at=at(9), old_expires_at=at(40), new_expires_at=at(35))

    entries = timeline(request(), [], [], [held()], True, hold_expiry_changes=[second, first])

    changes = [e for e in entries if e.action is HistoryAction.HOLD_EXPIRY_CHANGED]
    assert [e.source_id for e in changes] == [first.id, second.id]


@pytest.mark.story("SCRUM-136")
def test_a_change_at_the_same_instant_as_the_hold_follows_it_by_rank() -> None:
    """The SCRUM-88 tie-breaker, unchanged: equal times sort by the action's rank."""
    entries = timeline(
        request(), [], [], [held()], True, hold_expiry_changes=[change(changed_at=at(6))]
    )

    assert actions(entries) == [
        HistoryAction.DRAFT_CREATED,
        HistoryAction.VENUE_REQUESTED,
        HistoryAction.HOLD_CREATED,
        HistoryAction.HOLD_EXPIRY_CHANGED,
    ]


@pytest.mark.story("SCRUM-136")
def test_the_hold_entry_still_shows_the_latest_expiry() -> None:
    """AC6: the hold's own entry is SCRUM-88's, unchanged by any recorded change."""
    entries = timeline(
        request(), [], [], [held(expires_at=at(40))], True, hold_expiry_changes=[change()]
    )

    [hold] = [e for e in entries if e.action is HistoryAction.HOLD_CREATED]
    assert hold.hold_expires_at == at(40)


@pytest.mark.story("SCRUM-136")
def test_the_expiry_action_is_appended_without_moving_any_earlier_one() -> None:
    order = list(HistoryAction)

    assert order.index(HistoryAction.VENUE_CLOSED) == 29
    assert order[30:] == [HistoryAction.HOLD_EXPIRY_CHANGED]
