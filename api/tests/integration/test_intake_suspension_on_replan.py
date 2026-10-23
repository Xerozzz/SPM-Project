"""SCRUM-131: an approved change to a Confirmed event suspends registration intake."""

from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from domain.change_decision import Decision
from domain.registration_intake import RegistrationIntakeError
from domain.roles import Role
from domain.safety_review import SafetyDecision, fingerprint
from models.event_change_request import EventChangeRequest
from models.event_request import EventRequest
from models.user import User
from models.venue_booking import VenueBooking
from services import event_confirmations
from services import registration_intake as intake_service
from services import safety_reviews as safety_service
from tests.integration.test_event_confirmation import ready_event
from tests.integration.test_safety_approval_invalidation import (
    _confirmed,
    _decide,
    _session_change,
)
from tests.integration.test_safety_review import _NOW
from tests.integration.test_submit_event_request import MakeUser

_LATER = _NOW + timedelta(minutes=1)


def _open(db: Session, make_user: MakeUser) -> tuple[EventRequest, VenueBooking, User]:
    """A Confirmed event taking registrations until a day after `_NOW`."""
    event, booking, coordinator = _confirmed(db, make_user)
    event.registration_opened_at = _NOW
    event.registration_closes_at = _NOW + timedelta(days=1)
    db.flush()
    return event, booking, coordinator


def _stored(db: Session, event: EventRequest) -> EventRequest:
    db.expire_all()
    stored = db.get(EventRequest, event.id)
    assert stored is not None
    return stored


@pytest.mark.story("SCRUM-131")
def test_approving_a_change_to_a_confirmed_event_suspends_intake(
    db: Session, make_user: MakeUser
) -> None:
    event, booking, coordinator = _open(db, make_user)

    _decide(db, event, _session_change(db, event, booking), coordinator, Decision.APPROVE)

    stored = _stored(db, event)
    assert stored.registration_suspended_at == _NOW
    # The settings themselves are kept, only new intake stops.
    assert stored.registration_opened_at == _NOW
    assert stored.registration_closes_at == _NOW + timedelta(days=1)
    with pytest.raises(RegistrationIntakeError):
        intake_service.require_open_intake(stored, _LATER)


@pytest.mark.story("SCRUM-131")
def test_reconfirming_does_not_reopen_intake_but_the_organiser_can(
    db: Session, make_user: MakeUser
) -> None:
    event, booking, coordinator = _open(db, make_user)
    _decide(db, event, _session_change(db, event, booking), coordinator, Decision.APPROVE)
    plan = safety_service.plan_of(db, event, _LATER)
    officer = make_user(Role.SAFETY_OFFICER.value)
    safety_service.record(
        db, event, SafetyDecision.APPROVE, "Checked again", fingerprint(plan), officer.id, _LATER
    )

    event_confirmations.confirm(db, event, coordinator.id, _LATER)

    stored = _stored(db, event)
    assert stored.registration_suspended_at == _NOW
    with pytest.raises(RegistrationIntakeError):
        intake_service.require_open_intake(stored, _LATER)
    reopened = intake_service.open_intake(db, event.id, _NOW + timedelta(days=2), _LATER)
    assert reopened.registration_suspended_at is None
    intake_service.require_open_intake(reopened, _LATER)


@pytest.mark.story("SCRUM-131")
def test_rejecting_a_change_leaves_intake_open(db: Session, make_user: MakeUser) -> None:
    event, booking, coordinator = _open(db, make_user)

    _decide(db, event, _session_change(db, event, booking), coordinator, Decision.REJECT)

    stored = _stored(db, event)
    assert stored.registration_suspended_at is None
    intake_service.require_open_intake(stored, _LATER)


@pytest.mark.story("SCRUM-131")
def test_a_change_to_an_event_in_planning_leaves_intake_alone(
    db: Session, make_user: MakeUser
) -> None:
    event, booking, coordinator = ready_event(db, make_user)

    _decide(db, event, _session_change(db, event, booking), coordinator, Decision.APPROVE)

    assert _stored(db, event).registration_suspended_at is None


@pytest.mark.story("SCRUM-131")
def test_a_failed_suspension_rolls_the_whole_decision_back(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    event, booking, coordinator = _open(db, make_user)
    change_id = _session_change(db, event, booking)
    db.commit()

    def broken(*_: object) -> None:
        raise RuntimeError("database went away")

    monkeypatch.setattr(intake_service, "suspend", broken)
    with pytest.raises(RuntimeError):
        _decide(db, event, change_id, coordinator, Decision.APPROVE)
    db.rollback()
    monkeypatch.undo()

    stored = _stored(db, event)
    change = db.get(EventChangeRequest, change_id)
    assert change is not None and change.status == "pending"
    assert stored.registration_suspended_at is None
    assert stored.status == "confirmed"
