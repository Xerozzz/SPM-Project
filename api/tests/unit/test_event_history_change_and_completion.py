"""SCRUM-120: change requests and completion in the event history. Pure readers.

Old and new values travel as whitelisted, labelled `changes` (ADR-0064); dates are marked
`datetime` so the UI shows them in local time, never converted here (ADR-0068).
"""

import uuid
from dataclasses import replace
from typing import Any

import pytest

from domain.event_history import (
    ChangeItemRecord,
    ChangeRequestRecord,
    ClosureNoteRecord,
    FieldChange,
    FieldKind,
    HistoryAction,
    HistoryOutcome,
    HistorySource,
    ReplanCauseRecord,
    ReplanRecord,
    change_request_entries,
    completion_entries,
    timeline,
)
from domain.event_replanning import ReplanCause
from tests.unit.test_event_history import COORDINATOR, OWNER, actions, at, request

START_OLD, START_NEW = "2030-01-10T02:00:00+00:00", "2030-01-11T02:00:00+00:00"


def item(
    target: str, field: str, current: object, proposed: object, subject: str | None = None
) -> ChangeItemRecord:
    return ChangeItemRecord(target, field, current, proposed, subject)


def change_request(**overrides: Any) -> ChangeRequestRecord:
    """The Organiser asking at 10h to move the start, still pending."""
    record = ChangeRequestRecord(
        id=uuid.uuid4(),
        requested_by=OWNER,
        created_at=at(10),
        reason="Speaker moved",
        status="pending",
        decided_by=None,
        decided_at=None,
        decision_note=None,
        items=(item("event", "start_at", START_OLD, START_NEW),),
    )
    return replace(record, **overrides)


def note(version: int, attendance: int | None, notes: str | None) -> ClosureNoteRecord:
    return ClosureNoteRecord(
        uuid.uuid4(), version, attendance, notes, COORDINATOR, at(100 + version)
    )


# ------------------------------------------------------------ AC1 change requests


@pytest.mark.story("SCRUM-120")
def test_a_request_shows_the_requester_reason_and_each_value_old_and_new() -> None:
    [entry] = change_request_entries(change_request())

    assert (entry.action, entry.actor, entry.occurred_at, entry.reason) == (
        HistoryAction.CHANGE_REQUESTED,
        OWNER,
        at(10),
        "Speaker moved",
    )
    assert entry.source_type is HistorySource.EVENT_CHANGE_REQUEST
    assert entry.changes == (
        FieldChange(
            "event.start_at", "Start date and time", START_OLD, START_NEW, FieldKind.DATETIME
        ),
    )


@pytest.mark.story("SCRUM-120")
@pytest.mark.parametrize(
    ("status", "outcome"),
    [("approved", HistoryOutcome.APPROVED), ("rejected", HistoryOutcome.REJECTED)],
)
def test_a_decision_shows_the_decider_outcome_and_note_but_not_the_values_again(
    status: str, outcome: HistoryOutcome
) -> None:
    record = change_request(
        status=status, decided_by=COORDINATOR, decided_at=at(12), decision_note="Venue free"
    )

    requested, decided = change_request_entries(record)

    assert (decided.action, decided.actor, decided.occurred_at) == (
        HistoryAction.CHANGE_DECIDED,
        COORDINATOR,
        at(12),
    )
    assert (decided.outcome, decided.reason) == (outcome, "Venue free")
    assert decided.changes == ()
    assert len(requested.changes) == 1


@pytest.mark.story("SCRUM-120")
def test_a_pending_request_has_no_decision_entry() -> None:
    assert actions(change_request_entries(change_request())) == [HistoryAction.CHANGE_REQUESTED]


EVERY_ITEM = (
    item("event", "start_at", START_OLD, START_NEW),
    item("event", "end_at", START_OLD, START_NEW),
    item("event", "expected_attendance", 80, 120),
    item("event", "venue_requirement", "Hall A", "Hall B"),
    item("event", "accessibility_requirement", None, "Ramp"),
    item("event", "layout_requirement", "theatre", "banquet"),
    item("session", "session_label", "Morning", "Opening", "Morning"),
    item("session", "start_at", START_OLD, START_NEW, "Morning"),
    item("session", "end_at", START_OLD, START_NEW, "Morning"),
    item("equipment", "quantity", 2, 3, "Projector"),
    item("equipment", "technical_requirements", None, "HDMI", "Projector"),
    item(
        "equipment",
        "add",
        None,
        {"equipment_type": "Mic", "quantity": 2, "technical_requirements": None},
    ),
    item(
        "equipment",
        "remove",
        {"equipment_type": "Screen", "quantity": 1, "technical_requirements": "4K"},
        None,
    ),
)


@pytest.mark.story("SCRUM-120")
def test_the_change_request_reader_emits_exactly_its_whitelisted_fields() -> None:
    """ADR-0064 rule 1: adding a field to the history is a deliberate edit of this set."""
    [entry] = change_request_entries(change_request(items=EVERY_ITEM))

    assert [c.field for c in entry.changes] == [
        "event.start_at",
        "event.end_at",
        "event.expected_attendance",
        "event.venue_requirement",
        "event.accessibility_requirement",
        "event.layout_requirement",
        "session.session_label",
        "session.start_at",
        "session.end_at",
        "equipment.quantity",
        "equipment.technical_requirements",
        "equipment.add",
        "equipment.remove",
    ]
    assert {c.field for c in entry.changes if c.kind is FieldKind.DATETIME} == {
        "event.start_at",
        "event.end_at",
        "session.start_at",
        "session.end_at",
    }


@pytest.mark.story("SCRUM-120")
def test_an_item_outside_the_whitelist_is_never_shown() -> None:
    record = change_request(
        items=(item("event", "name", "Old", "New"), item("event", "organiser_id", "a", "b"))
    )

    [entry] = change_request_entries(record)

    assert entry.changes == ()


@pytest.mark.story("SCRUM-120")
def test_session_and_equipment_values_are_labelled_with_what_they_change() -> None:
    [entry] = change_request_entries(change_request(items=EVERY_ITEM[6:]))

    assert [(c.label, c.old, c.new) for c in entry.changes] == [
        ("Session “Morning”: name", "Morning", "Opening"),
        ("Session “Morning”: start", START_OLD, START_NEW),
        ("Session “Morning”: end", START_OLD, START_NEW),
        ("Projector: quantity", "2", "3"),
        ("Projector: technical requirements", None, "HDMI"),
        ("Mic: line added", None, "Mic × 2"),
        ("Screen: line removed", "Screen × 1 (4K)", None),
    ]


@pytest.mark.story("SCRUM-120")
def test_a_session_that_is_not_found_is_named_generically() -> None:
    [entry] = change_request_entries(
        change_request(items=(item("session", "start_at", START_OLD, START_NEW),))
    )

    assert entry.changes[0].label == "A session: start"


@pytest.mark.story("SCRUM-120")
def test_a_return_caused_by_a_change_links_its_decision_entry() -> None:
    record = change_request(status="approved", decided_by=COORDINATOR, decided_at=at(20))
    cause = ReplanCauseRecord(
        ReplanCause.CHANGE_REQUEST, COORDINATOR, at(20), f"change_decided:{record.id}"
    )
    replan = ReplanRecord(uuid.uuid4(), at(20), ReplanCause.CHANGE_REQUEST)

    entries = timeline(
        request(),
        [],
        [],
        [],
        True,
        replans=[replan],
        replan_causes=[cause],
        change_requests=[record],
    )

    [back] = [e for e in entries if e.action is HistoryAction.RETURNED_TO_PLANNING]
    assert back.related_entry_ids == (f"change_decided:{record.id}",)
    assert back.related_entry_ids[0] in {e.key for e in entries}


# ------------------------------------------------------------- AC5 completion


@pytest.mark.story("SCRUM-120")
def test_completion_carries_the_first_closure_record() -> None:
    record = request(completed_by=COORDINATOR, completed_at=at(101))

    [entry] = completion_entries(record, [note(1, 0, "Ran late")])

    assert (entry.action, entry.actor, entry.occurred_at) == (
        HistoryAction.EVENT_COMPLETED,
        COORDINATOR,
        at(101),
    )
    assert entry.changes == (
        FieldChange("actual_attendance", "Actual attendance", None, "0"),
        FieldChange("notes", "Operational notes and issues", None, "Ran late"),
    )


@pytest.mark.story("SCRUM-120")
def test_each_correction_shows_the_previous_version_as_old() -> None:
    record = request(completed_by=COORDINATOR, completed_at=at(101))
    versions = [note(3, 95, "Fire drill"), note(1, None, None), note(2, 90, None)]

    entries = completion_entries(record, versions)

    assert (
        actions(entries) == [HistoryAction.EVENT_COMPLETED] + [HistoryAction.CLOSURE_CORRECTED] * 2
    )
    assert [[(c.old, c.new) for c in e.changes] for e in entries[1:]] == [
        [(None, "90"), (None, None)],
        [("90", "95"), (None, "Fire drill")],
    ]
    assert {e.source_type for e in entries[1:]} == {HistorySource.EVENT_CLOSURE_NOTE}


@pytest.mark.story("SCRUM-120")
def test_the_completion_reader_emits_exactly_attendance_and_notes() -> None:
    record = request(completed_by=COORDINATOR, completed_at=at(101))

    entries = completion_entries(record, [note(1, 50, None), note(2, 60, "x")])

    for entry in entries:
        assert [c.field for c in entry.changes] == ["actual_attendance", "notes"]
        assert {c.kind for c in entry.changes} == {FieldKind.TEXT}


@pytest.mark.story("SCRUM-120")
def test_an_event_never_completed_has_no_completion_entries() -> None:
    assert completion_entries(request(), []) == []


# ------------------------------------------------------------------------ ordering


@pytest.mark.story("SCRUM-120")
def test_change_and_completion_actions_are_appended_without_moving_any_earlier_one() -> None:
    order = list(HistoryAction)

    assert order.index(HistoryAction.EVENT_CANCELLED) == 23
    assert order[24:] == [
        HistoryAction.CHANGE_REQUESTED,
        HistoryAction.CHANGE_DECIDED,
        HistoryAction.EVENT_COMPLETED,
        HistoryAction.CLOSURE_CORRECTED,
    ]
