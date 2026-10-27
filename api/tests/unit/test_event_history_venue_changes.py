"""SCRUM-119: venue change entries in the event history. Pure readers, no database."""

import uuid
from dataclasses import replace
from typing import Any

import pytest

from domain.event_history import (
    BookingRecord,
    BufferChangeRecord,
    FieldChange,
    HistoryAction,
    HistorySource,
    booking_entries,
    buffer_change_entry,
    timeline,
)
from domain.venue_booking import BookingStatus
from tests.unit.test_event_history import COORDINATOR, STAFF, actions, at, booking, request

REASON = "Speaker withdrew"


def buffer_change(**overrides: Any) -> BufferChangeRecord:
    """Hall A's setup going from 0 to 30 minutes, catching out one booking."""
    record = BufferChangeRecord(
        id=uuid.uuid4(),
        venue_name="Hall A",
        changed_by=STAFF,
        changed_at=at(7),
        old_setup_minutes=0,
        old_turnaround_minutes=15,
        new_setup_minutes=30,
        new_turnaround_minutes=15,
        affected_booking_ids=(uuid.uuid4(),),
    )
    return replace(record, **overrides)


def held(**overrides: Any) -> BookingRecord:
    """A request Venue Staff hold until 30h; pass field=value to move it on."""
    values: dict[str, Any] = {
        "status": BookingStatus.TENTATIVE,
        "held_by": STAFF,
        "held_at": at(6),
        "expires_at": at(30),
    }
    return booking(**(values | overrides))


# ------------------------------------------------------------------ AC4 session period


@pytest.mark.story("SCRUM-119")
def test_every_venue_entry_carries_its_session_label_and_period() -> None:
    record = booking(status=BookingStatus.EXPIRED, held_by=STAFF, held_at=at(6), expires_at=at(8))

    entries = booking_entries(record, None, None)

    assert len(entries) == 3
    for entry in entries:
        assert (entry.session_label, entry.session_start_at, entry.session_end_at) == (
            "Main session",
            at(100),
            at(102),
        )


# ---------------------------------------------------------------- AC1 cancellation


@pytest.mark.story("SCRUM-119")
def test_a_cancellation_names_the_coordinator_time_and_reason() -> None:
    record = held(
        status=BookingStatus.CANCELLED,
        cancelled_by=COORDINATOR,
        cancelled_at=at(9),
        cancellation_reason=REASON,
    )

    entries = booking_entries(record, None, None)
    cancelled = entries[-1]

    assert actions(entries) == [
        HistoryAction.VENUE_REQUESTED,
        HistoryAction.HOLD_CREATED,
        HistoryAction.ARRANGEMENT_CANCELLED,
    ]
    assert (cancelled.actor, cancelled.occurred_at, cancelled.reason) == (
        COORDINATOR,
        at(9),
        REASON,
    )
    assert (cancelled.source_type, cancelled.source_id) == (HistorySource.VENUE_BOOKING, record.id)
    assert cancelled.related_booking_id is None


@pytest.mark.story("SCRUM-119")
def test_a_booking_never_cancelled_has_no_cancellation_entry() -> None:
    assert HistoryAction.ARRANGEMENT_CANCELLED not in actions(booking_entries(held(), None, None))


# ------------------------------------------------------------------ AC3 replacement


@pytest.mark.story("SCRUM-119")
def test_a_replacement_request_and_its_adoption_name_the_original() -> None:
    original = uuid.uuid4()
    record = held(replaces_booking_id=original, adopted_by=COORDINATOR, adopted_at=at(9))

    entries = booking_entries(record, None, None)
    requested, adopted = entries[0], entries[-1]

    assert requested.action is HistoryAction.VENUE_REQUESTED
    assert requested.related_booking_id == original
    assert adopted.action is HistoryAction.REPLACEMENT_ADOPTED
    assert (adopted.actor, adopted.occurred_at, adopted.related_booking_id) == (
        COORDINATOR,
        at(9),
        original,
    )


@pytest.mark.story("SCRUM-119")
def test_adoption_gives_two_linked_entries_adopted_before_cancelled() -> None:
    """One action, two records: each record's own entry, at the same time, each naming
    the other arrangement, in a fixed order."""
    original = held(
        status=BookingStatus.CANCELLED,
        cancelled_by=COORDINATOR,
        cancelled_at=at(9),
        cancellation_reason="Replaced by an adopted replacement venue request",
    )
    replacement = held(replaces_booking_id=original.id, adopted_by=COORDINATOR, adopted_at=at(9))

    entries = timeline(request(), [], [], [original, replacement], False)
    at_nine = [e for e in entries if e.occurred_at == at(9)]

    assert [(e.action, e.source_id, e.related_booking_id) for e in at_nine] == [
        (HistoryAction.REPLACEMENT_ADOPTED, replacement.id, original.id),
        (HistoryAction.ARRANGEMENT_CANCELLED, original.id, replacement.id),
    ]
    assert len({e.key for e in entries}) == len(entries)


@pytest.mark.story("SCRUM-119")
def test_a_replacement_not_adopted_links_nothing_to_the_originals_cancellation() -> None:
    """The original was cancelled on its own; a pending replacement is no adoption."""
    original = held(
        status=BookingStatus.CANCELLED,
        cancelled_by=COORDINATOR,
        cancelled_at=at(9),
        cancellation_reason=REASON,
    )
    pending_replacement = booking(replaces_booking_id=original.id)

    entries = timeline(request(), [], [], [original, pending_replacement], False)

    [cancelled] = [e for e in entries if e.action is HistoryAction.ARRANGEMENT_CANCELLED]
    assert cancelled.related_booking_id is None


# --------------------------------------------------------------- AC2 expiry update gap


@pytest.mark.story("SCRUM-119")
def test_an_expiry_update_leaves_no_entry_and_the_hold_shows_the_latest_expiry() -> None:
    """ADR-0064 gap, pinned: an updated hold is indistinguishable from one placed with
    that expiry, because the update keeps no old value, actor or time."""
    updated = held(expires_at=at(50))

    entries = booking_entries(updated, None, None)

    assert actions(entries) == [HistoryAction.VENUE_REQUESTED, HistoryAction.HOLD_CREATED]
    assert entries[-1].hold_expires_at == at(50)


# ---------------------------------------------------------------- AC5 buffer change


@pytest.mark.story("SCRUM-119")
def test_a_buffer_change_shows_both_buffers_old_and_new_and_the_affected_booking() -> None:
    record = buffer_change()

    entry = buffer_change_entry(record)

    assert entry.action is HistoryAction.BUFFER_CHANGED
    assert (entry.actor, entry.occurred_at, entry.venue_name) == (STAFF, at(7), "Hall A")
    assert (entry.source_type, entry.source_id) == (HistorySource.VENUE_BUFFER_CHANGE, record.id)
    assert entry.affected_booking_ids == record.affected_booking_ids
    assert entry.changes == (
        FieldChange("setup_minutes", "Setup time (minutes)", "0", "30"),
        FieldChange("turnaround_minutes", "Turnaround time (minutes)", "15", "15"),
    )


@pytest.mark.story("SCRUM-119")
def test_the_buffer_reader_emits_exactly_its_whitelisted_fields() -> None:
    """ADR-0064 rule 1: adding a field to `changes` must be a deliberate edit here."""
    entry = buffer_change_entry(buffer_change())

    assert {c.field for c in entry.changes} == {"setup_minutes", "turnaround_minutes"}
    assert all(c.label for c in entry.changes)


@pytest.mark.story("SCRUM-119")
def test_buffer_changes_join_the_timeline_in_time_order() -> None:
    record = buffer_change(changed_at=at(5.5))

    entries = timeline(request(), [], [], [held()], False, [record])

    assert actions(entries) == [
        HistoryAction.DRAFT_CREATED,
        HistoryAction.VENUE_REQUESTED,
        HistoryAction.BUFFER_CHANGED,
        HistoryAction.HOLD_CREATED,
    ]


@pytest.mark.story("SCRUM-119")
def test_new_actions_rank_after_every_scrum_88_action() -> None:
    """The SCRUM-88 tie-breaker is unchanged: the new actions only extend it."""
    order = list(HistoryAction)

    assert order.index(HistoryAction.HOLD_EXPIRED) == 11
    assert order[12:15] == [
        HistoryAction.REPLACEMENT_ADOPTED,
        HistoryAction.ARRANGEMENT_CANCELLED,
        HistoryAction.BUFFER_CHANGED,
    ]
