"""SCRUM-130: an approved change to a Confirmed event invalidates its safety approval."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from domain.change_decision import Decision
from domain.event_confirmation import ConfirmationBlocker
from domain.event_status import EventStatus
from domain.roles import Role
from domain.safety_review import SafetyDecision, fingerprint
from models.event_change_request import EventChangeRequest
from models.event_request import EventRequest
from models.safety_review import SafetyReview
from models.user import User
from models.venue_booking import VenueBooking
from repositories import safety_reviews as safety_repo
from schemas.event_change_requests import EventChangeRequestCreate
from services import event_change_requests as change_service
from services import event_confirmations
from services import safety_reviews as safety_service
from tests.integration.test_event_confirmation import ready_event
from tests.integration.test_safety_review import _NOW
from tests.integration.test_submit_event_request import MakeClient, MakeUser


def _confirmed(db: Session, make_user: MakeUser) -> tuple[EventRequest, VenueBooking, User]:
    event, booking, coordinator = ready_event(db, make_user)
    event_confirmations.confirm(db, event, coordinator.id, _NOW)
    return event, booking, coordinator


def _session_change(db: Session, event: EventRequest, booking: VenueBooking) -> uuid.UUID:
    """A change to a session label only. It leaves the plan fingerprint as it was."""
    body = {
        "submission_key": str(uuid.uuid4()),
        "reason": "Renamed for the programme",
        "sessions": [{"booking_id": str(booking.id), "session_label": "Opening"}],
    }
    proposal = EventChangeRequestCreate.model_validate(body).to_proposal()
    created, _ = change_service.submit(
        db, event.id, event.organiser_id, proposal, uuid.uuid4(), _NOW
    )
    return created.id


def _decide(
    db: Session, event: EventRequest, change_id: uuid.UUID, user: User, decision: Decision
) -> None:
    change_service.decide(db, event.id, change_id, user.id, decision, "Reviewed", _NOW)


def _reviews(db: Session, event: EventRequest) -> list[SafetyReview]:
    db.expire_all()
    return safety_repo.list_for_event(db, event.id)


def _safety_reasons(db: Session, event: EventRequest) -> tuple[ConfirmationBlocker, ...]:
    return event_confirmations.readiness(db, event, _NOW).safety


@pytest.mark.story("SCRUM-130")
def test_approving_a_change_to_a_confirmed_event_invalidates_its_approval(
    db: Session, make_user: MakeUser
) -> None:
    event, booking, coordinator = _confirmed(db, make_user)
    change_id = _session_change(db, event, booking)

    _decide(db, event, change_id, coordinator, Decision.APPROVE)

    [review] = _reviews(db, event)
    assert review.invalidated_at == _NOW
    assert review.invalidation_cause == "change_request"
    standing = event_confirmations.standing_of(db, event)
    assert standing is not None and standing.invalidated
    assert event.status is EventStatus.APPROVED
    assert _safety_reasons(db, event) == (ConfirmationBlocker.SAFETY_APPROVAL_STALE,)


@pytest.mark.story("SCRUM-130")
def test_the_old_approval_stays_in_the_history(db: Session, make_user: MakeUser) -> None:
    event, booking, coordinator = _confirmed(db, make_user)
    [before] = _reviews(db, event)
    approved_by, approved_at = before.decided_by_id, before.decided_at

    _decide(db, event, _session_change(db, event, booking), coordinator, Decision.APPROVE)

    [after] = _reviews(db, event)
    assert (after.decision, after.decided_by_id, after.decided_at) == (
        "approve",
        approved_by,
        approved_at,
    )


@pytest.mark.story("SCRUM-130")
def test_a_new_approval_clears_the_way_to_reconfirm(db: Session, make_user: MakeUser) -> None:
    event, booking, coordinator = _confirmed(db, make_user)
    _decide(db, event, _session_change(db, event, booking), coordinator, Decision.APPROVE)

    # A minute later, so "the latest decision" has one answer.
    later = _NOW + timedelta(minutes=1)
    plan = safety_service.plan_of(db, event, later)
    officer = make_user(Role.SAFETY_OFFICER.value)
    safety_service.record(
        db, event, SafetyDecision.APPROVE, "Checked again", fingerprint(plan), officer.id, later
    )

    assert _safety_reasons(db, event) == ()
    assert len(_reviews(db, event)) == 2


@pytest.mark.story("SCRUM-130")
def test_rejecting_a_change_leaves_the_approval_as_it_was(db: Session, make_user: MakeUser) -> None:
    event, booking, coordinator = _confirmed(db, make_user)

    _decide(db, event, _session_change(db, event, booking), coordinator, Decision.REJECT)

    [review] = _reviews(db, event)
    assert review.invalidated_at is None
    assert event.status is EventStatus.CONFIRMED


@pytest.mark.story("SCRUM-130")
def test_a_change_to_an_event_in_planning_leaves_the_approval_as_it_was(
    db: Session, make_user: MakeUser
) -> None:
    event, booking, coordinator = ready_event(db, make_user)

    _decide(db, event, _session_change(db, event, booking), coordinator, Decision.APPROVE)

    [review] = _reviews(db, event)
    assert review.invalidated_at is None
    assert _safety_reasons(db, event) == ()


@pytest.mark.story("SCRUM-130")
def test_a_failed_invalidation_rolls_the_whole_decision_back(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    event, booking, coordinator = _confirmed(db, make_user)
    change_id = _session_change(db, event, booking)

    def broken(*_: object) -> list[SafetyReview]:
        raise RuntimeError("database went away")

    monkeypatch.setattr(safety_repo, "list_for_event", broken)
    with pytest.raises(RuntimeError):
        _decide(db, event, change_id, coordinator, Decision.APPROVE)
    db.rollback()
    monkeypatch.undo()

    [review] = _reviews(db, event)
    change = db.get(EventChangeRequest, change_id)
    assert change is not None and change.status == "pending"
    stored = db.get(EventRequest, event.id)
    assert stored is not None and stored.status is EventStatus.CONFIRMED
    assert review.invalidated_at is None


@pytest.mark.story("SCRUM-130")
async def test_the_history_shows_when_and_why_the_approval_stopped_counting(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, booking, coordinator = _confirmed(db, make_user)
    _decide(db, event, _session_change(db, event, booking), coordinator, Decision.APPROVE)

    async with make_client(coordinator) as client:
        response = await client.get(f"/api/safety-reviews/{event.id}/history")

    assert response.status_code == 200
    [row] = response.json()
    assert row["decision"] == "approve"
    assert row["invalidation_cause"] == "change_request"
    assert row["invalidated_at"] is not None
