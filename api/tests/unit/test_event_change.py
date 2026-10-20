"""SCRUM-37: the pure rules for a significant-change request."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from domain.event_change import (
    ADD,
    REMOVE,
    Catalogue,
    ChangeTarget,
    CurrentPlan,
    EquipmentProposal,
    PlannedSession,
    Proposal,
    Requirement,
    SessionProposal,
    accepts_change_request,
    plan_change,
)
from domain.event_status import EventStatus

NOW = datetime(2030, 1, 1, 9, tzinfo=UTC)
START = datetime(2030, 3, 1, 1, tzinfo=UTC)
END = START + timedelta(hours=6)
H = timedelta(hours=1)
# Deliberately naive: the rules must refuse a value without a time zone.
NAIVE = START.replace(tzinfo=None)
KEYNOTE = PlannedSession(uuid.uuid4(), "Keynote", START, START + 2 * H)
WORKSHOP = PlannedSession(uuid.uuid4(), "Workshop", START + 3 * H, START + 5 * H)
PROJECTOR = Requirement(uuid.uuid4(), "Projector", 2, "HDMI")
CATALOGUE = Catalogue(
    venue_names=["Hall A", "Hall B"], equipment_types=frozenset({"Projector", "Microphone"})
)
PLAN = CurrentPlan(
    event={
        "start_at": START,
        "end_at": END,
        "expected_attendance": 100,
        "venue_requirement": "Hall A",
        "accessibility_requirement": "Step-free access",
        "layout_requirement": "Theatre",
    },
    sessions=(KEYNOTE, WORKSHOP),
    equipment=(PROJECTOR,),
)


def _plan(proposal: Proposal) -> tuple[list[tuple[object, ...]], list[tuple[str, str]]]:
    items, problems = plan_change(proposal, PLAN, CATALOGUE, NOW)
    return (
        [(i.target, i.target_id, i.field, i.current, i.proposed) for i in items],
        [(p.field, p.reason) for p in problems],
    )


# --------------------------------------------------------------------------- AC1, AC7


@pytest.mark.story("SCRUM-37")
@pytest.mark.parametrize(
    "status", [EventStatus.SUBMITTED, EventStatus.APPROVED, EventStatus.CONFIRMED]
)
def test_submitted_approved_and_confirmed_events_accept_a_change_request(
    status: EventStatus,
) -> None:
    assert accepts_change_request(status)


@pytest.mark.story("SCRUM-37")
@pytest.mark.parametrize("status", [EventStatus.DRAFT, EventStatus.REJECTED])
def test_drafts_and_rejected_events_use_their_own_edit_flow(status: EventStatus) -> None:
    assert not accepts_change_request(status)


# --------------------------------------------------------------------------- AC2, AC3


@pytest.mark.story("SCRUM-37")
def test_each_changed_event_field_is_an_item_with_its_current_value() -> None:
    later = START + 24 * H
    items, problems = _plan(
        Proposal(
            reason="Venue double-booked",
            event={
                "start_at": later,
                "end_at": later + 6 * H,
                "expected_attendance": 150,
                "venue_requirement": "Hall B",
                "layout_requirement": "Banquet",
                "accessibility_requirement": "Step-free access and hearing loop",
            },
            sessions=(
                SessionProposal(KEYNOTE.id, start_at=later, end_at=later + 2 * H),
                SessionProposal(WORKSHOP.id, start_at=later + 3 * H, end_at=later + 5 * H),
            ),
        )
    )

    assert problems == []
    event_items = [i for i in items if i[0] is ChangeTarget.EVENT]
    assert (ChangeTarget.EVENT, None, "expected_attendance", 100, 150) in event_items
    assert (ChangeTarget.EVENT, None, "venue_requirement", "Hall A", "Hall B") in event_items
    assert len(event_items) == 6


@pytest.mark.story("SCRUM-37")
def test_an_unchanged_value_is_not_an_item() -> None:
    items, problems = _plan(
        Proposal(reason="r", event={"expected_attendance": 100, "layout_requirement": "Banquet"})
    )

    assert problems == []
    assert items == [(ChangeTarget.EVENT, None, "layout_requirement", "Theatre", "Banquet")]


@pytest.mark.story("SCRUM-37")
def test_a_session_change_keeps_its_old_label_and_period() -> None:
    items, problems = _plan(
        Proposal(
            reason="Keynote runs longer",
            sessions=(SessionProposal(KEYNOTE.id, session_label="Opening", end_at=START + 3 * H),),
        )
    )

    assert problems == []
    assert items == [
        (ChangeTarget.SESSION, KEYNOTE.id, "session_label", "Keynote", "Opening"),
        (ChangeTarget.SESSION, KEYNOTE.id, "end_at", START + 2 * H, START + 3 * H),
    ]


@pytest.mark.story("SCRUM-37")
def test_equipment_can_be_added_changed_and_removed() -> None:
    mic = EquipmentProposal(equipment_type="Microphone", quantity=4)
    more = EquipmentProposal(PROJECTOR.id, quantity=3, technical_requirements="HDMI and VGA")

    items, problems = _plan(Proposal(reason="Bigger room", equipment=(mic, more)))

    assert problems == []
    added = {"equipment_type": "Microphone", "quantity": 4, "technical_requirements": None}
    assert items == [
        (ChangeTarget.EQUIPMENT, None, ADD, None, added),
        (ChangeTarget.EQUIPMENT, PROJECTOR.id, "quantity", 2, 3),
        (ChangeTarget.EQUIPMENT, PROJECTOR.id, "technical_requirements", "HDMI", "HDMI and VGA"),
    ]

    items, problems = _plan(
        Proposal(reason="Not needed", equipment=(EquipmentProposal(PROJECTOR.id, remove=True),))
    )
    assert problems == []
    line = {"equipment_type": "Projector", "quantity": 2, "technical_requirements": "HDMI"}
    assert items == [(ChangeTarget.EQUIPMENT, PROJECTOR.id, REMOVE, line, None)]


@pytest.mark.story("SCRUM-37")
def test_a_removed_type_may_be_added_back_in_the_same_request() -> None:
    items, problems = _plan(
        Proposal(
            reason="Swap",
            equipment=(
                EquipmentProposal(PROJECTOR.id, remove=True),
                EquipmentProposal(equipment_type="Projector", quantity=5),
            ),
        )
    )

    assert problems == []
    assert [i[2] for i in items] == [REMOVE, ADD]


# --------------------------------------------------------------------------- AC1, AC4


@pytest.mark.story("SCRUM-37")
def test_a_blank_reason_is_refused() -> None:
    _, problems = _plan(Proposal(reason="   ", event={"expected_attendance": 120}))

    assert problems == [("reason", "is required")]


@pytest.mark.story("SCRUM-37")
def test_a_request_with_no_change_is_refused() -> None:
    _, problems = _plan(Proposal(reason="r", event={"expected_attendance": 100}))

    assert problems == [("changes", "must propose at least one change")]


@pytest.mark.story("SCRUM-37")
@pytest.mark.parametrize(
    ("name", "value", "reason"),
    [
        ("expected_attendance", 0, "must be a positive whole number"),
        ("expected_attendance", -5, "must be a positive whole number"),
        ("expected_attendance", True, "must be a positive whole number"),
        ("expected_attendance", None, "must be a positive whole number"),
        ("start_at", None, "is required"),
        ("start_at", NAIVE, "must include a timezone"),
        ("start_at", NOW, "must be in the future"),
        ("end_at", NAIVE + 8 * H, "must include a timezone"),
        ("venue_requirement", "Hall Z", "is not a catalogue option"),
        ("venue_requirement", None, "is required"),
        ("layout_requirement", "  ", "is required"),
        ("accessibility_requirement", None, "is required"),
    ],
)
def test_event_values_follow_the_creation_rules(name: str, value: object, reason: str) -> None:
    items, problems = _plan(Proposal(reason="r", event={name: value}))

    assert (f"event.{name}", reason) in problems
    assert items == []


@pytest.mark.story("SCRUM-37")
def test_the_end_must_stay_after_the_start() -> None:
    _, problems = _plan(Proposal(reason="r", event={"end_at": START}))

    assert ("event.end_at", "must be after the start") in problems


@pytest.mark.story("SCRUM-37")
def test_a_new_event_period_must_still_hold_the_sessions_left_alone() -> None:
    _, problems = _plan(Proposal(reason="Shorter day", event={"end_at": START + 4 * H}))

    assert problems == [
        (f"sessions.{WORKSHOP.id}", "session 'Workshop' would fall outside the event period")
    ]


@pytest.mark.story("SCRUM-37")
def test_session_values_follow_the_session_rules() -> None:
    _, problems = _plan(
        Proposal(
            reason="r",
            sessions=(
                SessionProposal(KEYNOTE.id, session_label="  "),
                SessionProposal(WORKSHOP.id, end_at=END + H),
            ),
        )
    )

    assert problems == [
        ("sessions[0].session_label", "must name the session"),
        ("sessions[1].end_at", "must not be after the event ends"),
    ]


@pytest.mark.story("SCRUM-37")
def test_an_unknown_or_repeated_session_is_refused() -> None:
    _, problems = _plan(
        Proposal(
            reason="r",
            sessions=(
                SessionProposal(uuid.uuid4(), session_label="X"),
                SessionProposal(KEYNOTE.id, session_label="A"),
                SessionProposal(KEYNOTE.id, session_label="B"),
            ),
        )
    )

    assert ("sessions[0].booking_id", "is not a session of this event") in problems
    assert ("sessions[1].booking_id", "is proposed more than once") in problems


@pytest.mark.story("SCRUM-37")
def test_sessions_are_not_checked_against_a_refused_event_period() -> None:
    _, problems = _plan(
        Proposal(
            reason="r",
            event={"start_at": NAIVE},
            sessions=(SessionProposal(KEYNOTE.id, session_label="A"),),
        )
    )

    assert problems == [("event.start_at", "must include a timezone")]


@pytest.mark.story("SCRUM-37")
def test_equipment_values_follow_the_requirement_rules() -> None:
    _, problems = _plan(
        Proposal(
            reason="r",
            equipment=(
                EquipmentProposal(equipment_type="Smoke machine", quantity=1),
                EquipmentProposal(equipment_type="Projector", quantity=1),
                EquipmentProposal(equipment_type="Microphone", quantity=0),
                EquipmentProposal(PROJECTOR.id, quantity=0),
            ),
        )
    )

    assert problems == [
        ("equipment[0].equipment_type", "is not an active catalogue type"),
        ("equipment[1].equipment_type", "is already required for this event"),
        ("equipment[2].quantity", "must be at least 1"),
        ("equipment[3].quantity", "must be at least 1"),
    ]


@pytest.mark.story("SCRUM-37")
def test_an_unknown_or_repeated_equipment_line_is_refused() -> None:
    _, problems = _plan(
        Proposal(
            reason="r",
            equipment=(
                EquipmentProposal(uuid.uuid4(), quantity=1),
                EquipmentProposal(PROJECTOR.id, quantity=3),
                EquipmentProposal(PROJECTOR.id, remove=True),
            ),
        )
    )

    assert ("equipment[0].requirement_id", "is not a current requirement") in problems
    assert ("equipment[2].requirement_id", "is proposed more than once") in problems


@pytest.mark.story("SCRUM-37")
def test_one_invalid_value_refuses_the_whole_request() -> None:
    items, problems = _plan(
        Proposal(
            reason="r",
            event={"expected_attendance": 0, "layout_requirement": "Banquet"},
            equipment=(EquipmentProposal(PROJECTOR.id, quantity=3),),
        )
    )

    # Items may still be listed, but the caller records nothing when there is a problem.
    assert problems == [("event.expected_attendance", "must be a positive whole number")]
    assert len(items) == 2
