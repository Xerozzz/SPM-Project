"""SCRUM-47: the pure rules for deciding a significant-change request."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from domain import event_status
from domain.change_decision import (
    AlreadyDecidedError,
    Decision,
    ItemOutcome,
    RecordedItem,
    decided_status,
    decision_problems,
    event_value,
    outcome_of,
    proposal_of,
    stale_items,
)
from domain.event_change import (
    ADD,
    REMOVE,
    ChangeRequestStatus,
    CurrentPlan,
    EquipmentProposal,
    PlannedSession,
    Requirement,
    SessionProposal,
)
from domain.event_status import EventAction, EventStatus, InvalidTransitionError
from domain.validation import FieldProblem

START = datetime(2030, 3, 1, 1, tzinfo=UTC)
H = timedelta(hours=1)
KEYNOTE = PlannedSession(uuid.uuid4(), "Keynote", START, START + 2 * H)
PROJECTOR = Requirement(uuid.uuid4(), "Projector", 2, "HDMI")
PLAN = CurrentPlan(
    event={"expected_attendance": 100, "start_at": START, "layout_requirement": "Theatre"},
    sessions=(KEYNOTE,),
    equipment=(PROJECTOR,),
)
LINE = {"equipment_type": "Projector", "quantity": 2, "technical_requirements": "HDMI"}


def _item(
    target: str, target_id: object, field: str, current: object, proposed: object
) -> RecordedItem:
    return RecordedItem(target, target_id, field, current, proposed)


# --------------------------------------------------------------------------- AC1, AC9


@pytest.mark.story("SCRUM-47")
def test_a_pending_request_needs_a_note() -> None:
    assert decision_problems(ChangeRequestStatus.PENDING, "  ") == [
        FieldProblem("note", "is required")
    ]
    assert decision_problems(ChangeRequestStatus.PENDING, "Fits the venue") == []


@pytest.mark.story("SCRUM-47")
@pytest.mark.parametrize("status", [ChangeRequestStatus.APPROVED, ChangeRequestStatus.REJECTED])
def test_a_decided_request_cannot_be_decided_again(status: ChangeRequestStatus) -> None:
    with pytest.raises(AlreadyDecidedError) as raised:
        decision_problems(status, "again")

    assert raised.value.status == status


@pytest.mark.story("SCRUM-47")
def test_each_decision_has_its_status() -> None:
    assert decided_status(Decision.APPROVE) is ChangeRequestStatus.APPROVED
    assert decided_status(Decision.REJECT) is ChangeRequestStatus.REJECTED


# --------------------------------------------------------------------------- AC2


@pytest.mark.story("SCRUM-47")
def test_items_that_still_match_the_plan_are_not_stale() -> None:
    items = [
        _item("event", None, "expected_attendance", 100, 150),
        _item("event", None, "start_at", START.isoformat(), (START + H).isoformat()),
        _item("session", KEYNOTE.id, "session_label", "Keynote", "Opening"),
        _item("equipment", PROJECTOR.id, "quantity", 2, 3),
        _item("equipment", PROJECTOR.id, REMOVE, LINE, None),
        _item("equipment", None, ADD, None, {"equipment_type": "Microphone"}),
    ]

    assert stale_items(items, PLAN) == []


@pytest.mark.story("SCRUM-47")
def test_a_value_changed_since_the_request_is_stale() -> None:
    items = [
        _item("event", None, "expected_attendance", 90, 150),
        _item("event", None, "layout_requirement", "Theatre", "Banquet"),
        _item("session", KEYNOTE.id, "end_at", (START + H).isoformat(), START.isoformat()),
        _item("equipment", PROJECTOR.id, "technical_requirements", "VGA", "HDMI"),
    ]

    assert stale_items(items, PLAN) == [
        FieldProblem("items[0]", "has changed since the request was made"),
        FieldProblem("items[2]", "has changed since the request was made"),
        FieldProblem("items[3]", "has changed since the request was made"),
    ]


@pytest.mark.story("SCRUM-47")
def test_a_session_or_line_that_is_gone_is_stale() -> None:
    items = [
        _item("session", uuid.uuid4(), "session_label", "Old", "New"),
        _item("equipment", uuid.uuid4(), "quantity", 1, 2),
        _item("equipment", uuid.uuid4(), REMOVE, LINE, None),
    ]

    assert len(stale_items(items, PLAN)) == 3


# --------------------------------------------------------------------------- AC3


@pytest.mark.story("SCRUM-47")
def test_the_proposal_is_rebuilt_from_its_items() -> None:
    new_line = {"equipment_type": "Microphone", "quantity": 4, "technical_requirements": None}
    other = uuid.uuid4()
    items = [
        _item("event", None, "start_at", START.isoformat(), (START + H).isoformat()),
        _item("event", None, "expected_attendance", 100, 150),
        _item("session", KEYNOTE.id, "session_label", "Keynote", "Opening"),
        _item("session", KEYNOTE.id, "end_at", "x", (START + 3 * H).isoformat()),
        _item("equipment", PROJECTOR.id, "quantity", 2, 3),
        _item("equipment", other, REMOVE, LINE, None),
        _item("equipment", None, ADD, None, new_line),
    ]

    proposal = proposal_of("Bigger crowd", items)

    assert proposal.reason == "Bigger crowd"
    assert proposal.event == {"start_at": START + H, "expected_attendance": 150}
    assert proposal.sessions == (
        SessionProposal(KEYNOTE.id, session_label="Opening", end_at=START + 3 * H),
    )
    assert proposal.equipment == (
        EquipmentProposal(PROJECTOR.id, quantity=3),
        EquipmentProposal(other, remove=True),
        EquipmentProposal(equipment_type="Microphone", quantity=4),
    )


@pytest.mark.story("SCRUM-47")
def test_event_fields_are_applied_and_arrangements_need_replanning() -> None:
    event_item = _item("event", None, "start_at", "a", (START + H).isoformat())

    assert outcome_of(event_item) is ItemOutcome.APPLIED
    assert event_value(event_item) == START + H
    assert event_value(_item("event", None, "expected_attendance", 1, 2)) == 2
    assert outcome_of(_item("session", KEYNOTE.id, "end_at", "a", "b")) is (
        ItemOutcome.NEEDS_REPLANNING
    )
    assert outcome_of(_item("equipment", None, ADD, None, LINE)) is ItemOutcome.NEEDS_REPLANNING


# --------------------------------------------------------------------------- AC5


@pytest.mark.story("SCRUM-47")
def test_an_approved_change_returns_a_confirmed_event_to_planning() -> None:
    assert event_status.replan(EventStatus.CONFIRMED) is EventStatus.APPROVED
    assert EventAction.REPLAN in event_status.allowed_actions(EventStatus.CONFIRMED)
    with pytest.raises(InvalidTransitionError):
        event_status.replan(EventStatus.SUBMITTED)
