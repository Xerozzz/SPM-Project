"""SCRUM-79: when a plan may be reviewed, and whether a decision still applies to it.

Pure, so every rule gets its own fast test (AGENTS.md section 4). The arrangement
throughout is one held venue and one fully arranged piece of equipment, which is the
only state AC2 lets a review begin from; each test breaks exactly one thing.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from domain.equipment_requirement import RequirementReview
from domain.equipment_reservation import ReservationState
from domain.safety_review import (
    PlannedEquipment,
    PlannedVenue,
    PlanSnapshot,
    ReviewBlocker,
    SafetyDecision,
    blockers,
    fingerprint,
    is_stale,
    latest_outstanding,
    may_review,
    returns_to_coordinator,
)
from domain.venue_booking import BookingStatus

_START = datetime(2030, 3, 4, 10, tzinfo=UTC)


def venue(**overrides: Any) -> PlannedVenue:
    values: dict[str, Any] = {
        "booking_id": uuid.UUID(int=1),
        "venue_id": uuid.UUID(int=10),
        "session_label": "Main hall",
        "start_at": _START,
        "end_at": _START + timedelta(hours=2),
        "status": BookingStatus.TENTATIVE,
        "hold_expired": False,
    }
    values.update(overrides)
    return PlannedVenue(**values)


def equipment(**overrides: Any) -> PlannedEquipment:
    values: dict[str, Any] = {
        "requirement_id": uuid.UUID(int=2),
        "equipment_type": "Projector",
        "quantity": 2,
        "review_status": RequirementReview.AVAILABLE,
        "reservation_state": ReservationState.RESERVED,
        "has_flagged_reservation": False,
    }
    values.update(overrides)
    return PlannedEquipment(**values)


def plan(**overrides: Any) -> PlanSnapshot:
    """A plan that may be reviewed; pass a field to break exactly one thing."""
    values: dict[str, Any] = {
        "expected_attendance": 150,
        "accessibility_requirement": "Step-free access",
        "layout_requirement": "Theatre",
        "event_start_at": _START,
        "event_end_at": _START + timedelta(hours=2),
        "venues": [venue()],
        "equipment": [equipment()],
    }
    values.update(overrides)
    return PlanSnapshot(**values)


# --------------------------------------------------------------------------- AC2


@pytest.mark.story("SCRUM-79")
def test_a_fully_arranged_plan_may_be_reviewed() -> None:
    assert blockers(plan()) == []
    assert may_review(plan()) is True


@pytest.mark.story("SCRUM-79")
def test_an_event_with_no_venue_arrangement_has_nothing_to_judge() -> None:
    assert blockers(plan(venues=[])) == [ReviewBlocker.NO_VENUE_ARRANGEMENT]


@pytest.mark.story("SCRUM-79")
@pytest.mark.parametrize(
    "status",
    [BookingStatus.PENDING, BookingStatus.REJECTED, BookingStatus.CANCELLED, BookingStatus.EXPIRED],
)
def test_a_venue_that_is_not_held_blocks_review(status: BookingStatus) -> None:
    # SCRUM-110 made approval a hold, so anything short of tentative or confirmed means
    # the venue is not actually arranged.
    assert blockers(plan(venues=[venue(status=status)])) == [ReviewBlocker.VENUE_NOT_HELD]


@pytest.mark.story("SCRUM-79")
def test_a_confirmed_booking_still_counts_as_arranged() -> None:
    # Rows confirmed under the pre-SCRUM-110 flow are untouched and still hold the venue.
    assert blockers(plan(venues=[venue(status=BookingStatus.CONFIRMED)])) == []


@pytest.mark.story("SCRUM-79")
def test_an_expired_hold_blocks_review_and_says_so() -> None:
    # Reported distinctly from "not held": the Coordinator's fix is different, and
    # ADR-0030 means a run-out hold can still read as tentative until it is swept.
    assert blockers(plan(venues=[venue(hold_expired=True)])) == [ReviewBlocker.HOLD_EXPIRED]


@pytest.mark.story("SCRUM-79")
def test_an_expired_flag_on_a_confirmed_booking_is_ignored() -> None:
    # Only a hold expires. A confirmed booking carrying a stale flag is still arranged.
    assert blockers(plan(venues=[venue(status=BookingStatus.CONFIRMED, hold_expired=True)])) == []


@pytest.mark.story("SCRUM-79")
def test_equipment_waiting_for_review_blocks() -> None:
    waiting = equipment(review_status=RequirementReview.PENDING_REVIEW)

    assert blockers(plan(equipment=[waiting])) == [ReviewBlocker.EQUIPMENT_UNREVIEWED]


@pytest.mark.story("SCRUM-79")
@pytest.mark.parametrize(
    "review",
    [RequirementReview.PARTIALLY_AVAILABLE, RequirementReview.UNAVAILABLE],
)
def test_equipment_that_cannot_be_met_blocks(review: RequirementReview) -> None:
    # AC2 calls both partial and unresolved a blocker.
    assert blockers(plan(equipment=[equipment(review_status=review)])) == [
        ReviewBlocker.EQUIPMENT_NOT_FULFILLED
    ]


@pytest.mark.story("SCRUM-79")
@pytest.mark.parametrize(
    "state", [ReservationState.NOT_RESERVED, ReservationState.PARTIALLY_RESERVED]
)
def test_equipment_judged_available_but_not_secured_blocks(state: ReservationState) -> None:
    """AC2's "partial" case, and the interpretation worth arguing about.

    Reviewed as available says Technical Support believe it can be met; reserved says
    they have committed it. A plan whose equipment is only believed-in is not one to
    certify as safe, so both halves have to be done.
    """
    assert blockers(plan(equipment=[equipment(reservation_state=state)])) == [
        ReviewBlocker.EQUIPMENT_NOT_FULFILLED
    ]


@pytest.mark.story("SCRUM-79")
def test_a_flagged_reservation_blocks_until_reconsidered() -> None:
    # SCRUM-43 AC6: the requirement moved after it was reserved, so what is held no
    # longer matches what is needed.
    assert blockers(plan(equipment=[equipment(has_flagged_reservation=True)])) == [
        ReviewBlocker.RESERVATION_NEEDS_RECONSIDERING
    ]


@pytest.mark.story("SCRUM-79")
def test_every_reason_is_reported_at_once() -> None:
    # A Coordinator fixing one at a time learns about the next only after another round
    # trip. Same rule SCRUM-59 set for venues.
    found = blockers(
        plan(
            venues=[venue(hold_expired=True)],
            equipment=[equipment(review_status=RequirementReview.PENDING_REVIEW)],
        )
    )

    assert found == [ReviewBlocker.HOLD_EXPIRED, ReviewBlocker.EQUIPMENT_UNREVIEWED]


@pytest.mark.story("SCRUM-79")
def test_the_same_reason_twice_is_reported_once() -> None:
    # Three expired holds is one thing to go and fix.
    found = blockers(
        plan(
            venues=[
                venue(booking_id=uuid.UUID(int=1), hold_expired=True),
                venue(booking_id=uuid.UUID(int=2), hold_expired=True),
            ]
        )
    )

    assert found == [ReviewBlocker.HOLD_EXPIRED]


# ----------------------------------------------------------------- AC4 and AC7


@pytest.mark.story("SCRUM-79")
def test_the_same_plan_fingerprints_the_same() -> None:
    assert fingerprint(plan()) == fingerprint(plan())


@pytest.mark.story("SCRUM-79")
def test_the_order_rows_arrive_in_does_not_change_the_fingerprint() -> None:
    # Two bookings, listed either way round, are the same plan.
    first, second = venue(booking_id=uuid.UUID(int=1)), venue(booking_id=uuid.UUID(int=2))

    assert fingerprint(plan(venues=[first, second])) == fingerprint(plan(venues=[second, first]))


@pytest.mark.story("SCRUM-79")
@pytest.mark.parametrize(
    "change",
    [
        {"expected_attendance": 151},
        {"accessibility_requirement": "None"},
        {"layout_requirement": "Classroom"},
        {"event_start_at": _START + timedelta(minutes=1)},
        {"event_end_at": _START + timedelta(hours=3)},
        {"venues": [venue(venue_id=uuid.UUID(int=99))]},
        {"venues": [venue(start_at=_START + timedelta(minutes=30))]},
        {"venues": [venue(session_label="Breakout")]},
        {"venues": [venue(status=BookingStatus.CONFIRMED)]},
        {"venues": [venue(hold_expired=True)]},
        {"venues": []},
        {"equipment": [equipment(quantity=3)]},
        {"equipment": [equipment(equipment_type="Microphone")]},
        {"equipment": [equipment(review_status=RequirementReview.UNAVAILABLE)]},
        {"equipment": [equipment(reservation_state=ReservationState.NOT_RESERVED)]},
        {"equipment": [equipment(has_flagged_reservation=True)]},
        {"equipment": []},
    ],
)
def test_anything_that_could_change_the_judgement_changes_the_fingerprint(
    change: dict[str, Any],
) -> None:
    """Every field in the snapshot, one at a time.

    A field that could move without the fingerprint moving is a plan that can change
    under an approval, which is exactly what AC7 forbids.
    """
    assert fingerprint(plan()) != fingerprint(plan(**change))


@pytest.mark.story("SCRUM-79")
def test_a_decision_is_stale_once_the_plan_moves() -> None:
    taken_against = fingerprint(plan())

    assert is_stale(taken_against, fingerprint(plan())) is False
    assert is_stale(taken_against, fingerprint(plan(expected_attendance=200))) is True


# --------------------------------------------------------------------------- AC5


@pytest.mark.story("SCRUM-79")
@pytest.mark.parametrize(
    ("decision", "returns"),
    [
        (SafetyDecision.APPROVE, False),
        (SafetyDecision.REJECT, True),
        (SafetyDecision.REQUEST_CHANGES, True),
    ],
)
def test_which_decisions_send_the_plan_back(decision: SafetyDecision, returns: bool) -> None:
    assert returns_to_coordinator(decision) is returns


@pytest.mark.story("SCRUM-79")
def test_the_three_decisions_are_the_whole_vocabulary() -> None:
    # Written down once, so a fourth outcome is a deliberate change rather than a
    # surprise that behaves like an approval.
    assert {decision.value for decision in SafetyDecision} == {
        "approve",
        "reject",
        "request_changes",
    }


@pytest.mark.story("SCRUM-79")
def test_nothing_is_outstanding_before_any_decision() -> None:
    assert latest_outstanding([]) is None


@pytest.mark.story("SCRUM-79")
def test_a_rejection_is_outstanding_until_something_follows_it() -> None:
    assert latest_outstanding([SafetyDecision.REJECT]) is SafetyDecision.REJECT
    assert latest_outstanding([SafetyDecision.REQUEST_CHANGES]) is SafetyDecision.REQUEST_CHANGES


@pytest.mark.story("SCRUM-79")
def test_an_approval_clears_what_came_before_it() -> None:
    # Derived rather than stored (ADR-0033's choice for a flagged reservation): the
    # approval clears the rejection with no second write, so nothing is left behind.
    assert latest_outstanding([SafetyDecision.REJECT, SafetyDecision.APPROVE]) is None


@pytest.mark.story("SCRUM-79")
def test_only_the_latest_decision_counts() -> None:
    history = [SafetyDecision.APPROVE, SafetyDecision.REJECT]

    assert latest_outstanding(history) is SafetyDecision.REJECT
