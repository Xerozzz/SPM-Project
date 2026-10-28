"""SCRUM-119 AC6: equipment entries in the event history. Pure readers, no database."""

import uuid
from dataclasses import replace
from typing import Any

import pytest

from domain.event_history import (
    FieldChange,
    HistoryAction,
    HistorySource,
    Person,
    RequirementChangeRecord,
    ReservationRecord,
    requirement_change_entry,
    reservation_entries,
    timeline,
)
from tests.unit.test_event_history import COORDINATOR, actions, at, request

TECH = Person(uuid.uuid4(), "tech@example.com")


def change(**overrides: Any) -> RequirementChangeRecord:
    """Two projectors becoming three, with the cable note kept."""
    record = RequirementChangeRecord(
        id=uuid.uuid4(),
        action="updated",
        equipment_type="Projector",
        changed_by=COORDINATOR,
        changed_at=at(8),
        old_quantity=2,
        new_quantity=3,
        old_technical_requirements="HDMI cable",
        new_technical_requirements="HDMI cable",
    )
    return replace(record, **overrides)


def reservation(**overrides: Any) -> ReservationRecord:
    """Two projectors reserved by Technical Support at 6h, still live."""
    record = ReservationRecord(
        id=uuid.uuid4(),
        equipment_type="Projector",
        quantity=2,
        reserved_by=TECH,
        reserved_at=at(6),
        flagged_at=None,
        released_by=None,
        released_at=None,
    )
    return replace(record, **overrides)


# --------------------------------------------------------------- requirement changes


@pytest.mark.story("SCRUM-119")
def test_an_update_shows_quantity_and_technical_requirements_old_and_new() -> None:
    record = change()

    entry = requirement_change_entry(record)

    assert entry.action is HistoryAction.REQUIREMENT_UPDATED
    assert (entry.actor, entry.occurred_at, entry.equipment_type) == (
        COORDINATOR,
        at(8),
        "Projector",
    )
    assert (entry.source_type, entry.source_id) == (
        HistorySource.EQUIPMENT_REQUIREMENT_CHANGE,
        record.id,
    )
    assert entry.changes == (
        FieldChange("quantity", "Quantity", "2", "3"),
        FieldChange("technical_requirements", "Technical requirements", "HDMI cable", "HDMI cable"),
    )


@pytest.mark.story("SCRUM-119")
def test_an_addition_has_no_old_values_and_a_removal_no_new_ones() -> None:
    added = requirement_change_entry(
        change(action="added", old_quantity=None, old_technical_requirements=None)
    )
    removed = requirement_change_entry(
        change(action="removed", new_quantity=None, new_technical_requirements=None)
    )

    assert added.action is HistoryAction.REQUIREMENT_ADDED
    assert [(c.old, c.new) for c in added.changes] == [(None, "3"), (None, "HDMI cable")]
    assert removed.action is HistoryAction.REQUIREMENT_REMOVED
    assert [(c.old, c.new) for c in removed.changes] == [("2", None), ("HDMI cable", None)]


@pytest.mark.story("SCRUM-119")
def test_the_requirement_reader_emits_exactly_its_whitelisted_fields() -> None:
    """ADR-0064 rule 1: adding a field to `changes` must be a deliberate edit here."""
    for action in ("added", "updated", "removed"):
        entry = requirement_change_entry(change(action=action))

        assert {c.field for c in entry.changes} == {"quantity", "technical_requirements"}
        assert all(c.label for c in entry.changes)


# ---------------------------------------------------------------------- reservations


@pytest.mark.story("SCRUM-119")
def test_a_live_reservation_is_one_entry_with_its_quantity_and_who() -> None:
    record = reservation()

    [entry] = reservation_entries(record)

    assert entry.action is HistoryAction.EQUIPMENT_RESERVED
    assert (entry.actor, entry.occurred_at, entry.equipment_type, entry.quantity) == (
        TECH,
        at(6),
        "Projector",
        2,
    )
    assert (entry.source_type, entry.source_id) == (
        HistorySource.EQUIPMENT_RESERVATION,
        record.id,
    )
    assert entry.changes == ()


@pytest.mark.story("SCRUM-119")
def test_a_flag_is_the_systems_and_a_release_names_who_released_it() -> None:
    record = reservation(flagged_at=at(8), released_by=COORDINATOR, released_at=at(9))

    entries = reservation_entries(record)
    reserved, flagged, released = entries

    assert actions(entries) == [
        HistoryAction.EQUIPMENT_RESERVED,
        HistoryAction.RESERVATION_FLAGGED,
        HistoryAction.RESERVATION_RELEASED,
    ]
    assert (flagged.actor, flagged.occurred_at, flagged.quantity) == (None, at(8), 2)
    assert (released.actor, released.occurred_at, released.quantity) == (COORDINATOR, at(9), 2)


@pytest.mark.story("SCRUM-119")
def test_a_released_but_never_flagged_reservation_has_no_flag_entry() -> None:
    record = reservation(released_by=COORDINATOR, released_at=at(9))

    assert actions(reservation_entries(record)) == [
        HistoryAction.EQUIPMENT_RESERVED,
        HistoryAction.RESERVATION_RELEASED,
    ]


# -------------------------------------------------------------------------- timeline


@pytest.mark.story("SCRUM-119")
def test_a_change_ranks_before_the_flag_it_raises_in_the_same_instant() -> None:
    """The requirement change and its flag share one commit time; the change comes first,
    and every key is still unique."""
    flagged = reservation(flagged_at=at(8))

    entries = timeline(request(), [], [], [], False, (), [change()], [flagged])

    assert actions(entries) == [
        HistoryAction.DRAFT_CREATED,
        HistoryAction.EQUIPMENT_RESERVED,
        HistoryAction.REQUIREMENT_UPDATED,
        HistoryAction.RESERVATION_FLAGGED,
    ]
    assert len({e.key for e in entries}) == len(entries)


@pytest.mark.story("SCRUM-119")
def test_equipment_actions_extend_the_order_without_moving_any_earlier_one() -> None:
    order = list(HistoryAction)

    assert order.index(HistoryAction.BUFFER_CHANGED) == 14
    # SCRUM-120 appends after these, so they are pinned as a slice, not as the tail.
    assert order[15:21] == [
        HistoryAction.REQUIREMENT_ADDED,
        HistoryAction.REQUIREMENT_UPDATED,
        HistoryAction.REQUIREMENT_REMOVED,
        HistoryAction.EQUIPMENT_RESERVED,
        HistoryAction.RESERVATION_FLAGGED,
        HistoryAction.RESERVATION_RELEASED,
    ]
