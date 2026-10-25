"""SCRUM-50: event change, safety and lifecycle notifications."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.change_decision import Decision
from domain.notifications import NotificationType
from domain.roles import Role
from domain.safety_review import SafetyDecision, fingerprint
from domain.venue_unavailability import VenueUnavailabilityFields
from models.event_request import EventRequest
from models.notification import Notification
from models.user import User
from services import event_change_requests as change_service
from services import event_completions, event_confirmations, event_registrations
from services import safety_reviews as safety_service
from services import venue_unavailabilities as closures
from tests.integration.test_event_confirmation import approve_safety, ready_event
from tests.integration.test_safety_approval_invalidation import _confirmed, _session_change
from tests.integration.test_safety_review import _NOW, arranged_event
from tests.integration.test_submit_event_request import MakeClient, MakeUser

_H = timedelta(hours=1)


def _got(db: Session, user_id: uuid.UUID | None, kind: NotificationType) -> int:
    """How many notifications of this kind this person has."""
    db.expire_all()
    statement = select(Notification).where(
        Notification.recipient_id == user_id, Notification.type == kind.value
    )
    return len(list(db.scalars(statement)))


def _organiser(db: Session, event: EventRequest) -> User:
    user = db.get(User, event.organiser_id)
    assert user is not None
    return user


def _register(db: Session, event: EventRequest, make_user: MakeUser) -> User:
    attendee = make_user("attendee")
    event.registration_opened_at = _NOW
    db.flush()
    event_registrations.submit(
        db, event.id, attendee.id, "Ada Lovelace", 24, "+65 8123 4567", None, _NOW
    )
    return attendee


# --------------------------------------------------------------------------- AC1


@pytest.mark.story("SCRUM-50")
def test_a_proposal_notifies_the_coordinator_once(db: Session, make_user: MakeUser) -> None:
    event, booking, coordinator = ready_event(db, make_user)

    _session_change(db, event, booking)

    assert _got(db, coordinator.id, NotificationType.CHANGE_PROPOSED) == 1
    assert _got(db, event.organiser_id, NotificationType.CHANGE_PROPOSED) == 0


@pytest.mark.story("SCRUM-50")
@pytest.mark.parametrize(
    ("decision", "kind"),
    [
        (Decision.APPROVE, NotificationType.CHANGE_APPROVED),
        (Decision.REJECT, NotificationType.CHANGE_REJECTED),
    ],
)
def test_a_decision_notifies_the_organiser_with_its_outcome(
    decision: Decision, kind: NotificationType, db: Session, make_user: MakeUser
) -> None:
    event, booking, coordinator = ready_event(db, make_user)
    change_id = _session_change(db, event, booking)

    change_service.decide(db, event.id, change_id, coordinator.id, decision, "ok", _NOW)

    assert _got(db, event.organiser_id, kind) == 1


@pytest.mark.story("SCRUM-50")
def test_a_rolled_back_decision_notifies_nobody(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    event, booking, coordinator = ready_event(db, make_user)
    change_id = _session_change(db, event, booking)
    db.commit()

    def broken(*_: object) -> None:
        raise RuntimeError("database went away")

    monkeypatch.setattr(change_service, "decided_status", broken)
    with pytest.raises(RuntimeError):
        change_service.decide(db, event.id, change_id, coordinator.id, Decision.APPROVE, "ok", _NOW)
    db.rollback()

    assert _got(db, event.organiser_id, NotificationType.CHANGE_APPROVED) == 0


# --------------------------------------------------------------------------- AC2


@pytest.mark.story("SCRUM-50")
async def test_a_ready_plan_is_announced_once_per_version(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    officer = make_user(Role.SAFETY_OFFICER.value)
    retired = make_user(Role.SAFETY_OFFICER.value, is_active=False)
    event, _, coordinator = arranged_event(db, make_user)
    url = f"/api/event-requests/{event.id}/confirmation"

    async with make_client(coordinator) as client:
        await client.get(url)
        await client.get(url)
    assert _got(db, officer.id, NotificationType.SAFETY_REVIEW_DUE) == 1
    assert _got(db, retired.id, NotificationType.SAFETY_REVIEW_DUE) == 0

    # A changed plan is a new version, so it is announced again.
    event.expected_attendance = (event.expected_attendance or 0) + 10
    db.flush()
    async with make_client(coordinator) as client:
        await client.get(url)
    assert _got(db, officer.id, NotificationType.SAFETY_REVIEW_DUE) == 2


@pytest.mark.story("SCRUM-50")
async def test_a_plan_already_decided_is_not_announced(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    officer = make_user(Role.SAFETY_OFFICER.value)
    event, _, coordinator = ready_event(db, make_user)

    async with make_client(coordinator) as client:
        await client.get(f"/api/event-requests/{event.id}/confirmation")

    assert _got(db, officer.id, NotificationType.SAFETY_REVIEW_DUE) == 0


@pytest.mark.story("SCRUM-50")
async def test_a_plan_not_ready_for_review_is_not_announced(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    officer = make_user(Role.SAFETY_OFFICER.value)
    event, _, coordinator = arranged_event(db, make_user, reserve=False)

    async with make_client(coordinator) as client:
        await client.get(f"/api/event-requests/{event.id}/confirmation")

    assert _got(db, officer.id, NotificationType.SAFETY_REVIEW_DUE) == 0


# --------------------------------------------------------------------------- AC3, AC4


@pytest.mark.story("SCRUM-50")
def test_a_safety_decision_reaches_the_organiser_and_coordinator(
    db: Session, make_user: MakeUser
) -> None:
    event, _, coordinator = arranged_event(db, make_user)
    plan = safety_service.plan_of(db, event, _NOW)
    safety_service.record(
        db,
        event,
        SafetyDecision.REJECT,
        "Exit blocked",
        fingerprint(plan),
        make_user(Role.SAFETY_OFFICER.value).id,
        _NOW,
    )

    assert _got(db, event.organiser_id, NotificationType.SAFETY_REJECTED) == 1
    assert _got(db, coordinator.id, NotificationType.SAFETY_REJECTED) == 1


@pytest.mark.story("SCRUM-50")
def test_confirmation_notifies_both_but_safety_approval_alone_does_not(
    db: Session, make_user: MakeUser
) -> None:
    event, _, coordinator = arranged_event(db, make_user)
    approve_safety(db, event, make_user)
    assert _got(db, event.organiser_id, NotificationType.EVENT_CONFIRMED) == 0

    event_confirmations.confirm(db, event, coordinator.id, _NOW)

    assert _got(db, event.organiser_id, NotificationType.EVENT_CONFIRMED) == 1
    assert _got(db, coordinator.id, NotificationType.EVENT_CONFIRMED) == 1


@pytest.mark.story("SCRUM-50")
def test_one_person_in_two_roles_is_notified_once(db: Session, make_user: MakeUser) -> None:
    event, _, coordinator = arranged_event(db, make_user)
    event.organiser_id = coordinator.id
    db.flush()
    approve_safety(db, event, make_user)

    event_confirmations.confirm(db, event, coordinator.id, _NOW)

    assert _got(db, coordinator.id, NotificationType.EVENT_CONFIRMED) == 1


# --------------------------------------------------------------------------- AC5


@pytest.mark.story("SCRUM-50")
def test_an_approved_change_tells_affected_staff_and_attendees(
    db: Session, make_user: MakeUser
) -> None:
    event, booking, coordinator = _confirmed(db, make_user)
    attendee = _register(db, event, make_user)
    bystander = make_user("attendee")
    change_id = _session_change(db, event, booking)

    change_service.decide(db, event.id, change_id, coordinator.id, Decision.APPROVE, "ok", _NOW)

    assert _got(db, attendee.id, NotificationType.EVENT_REPLANNED) == 1
    assert _got(db, booking.held_by_id, NotificationType.EVENT_REPLANNED) == 1
    assert _got(db, bystander.id, NotificationType.EVENT_REPLANNED) == 0
    assert _got(db, coordinator.id, NotificationType.EVENT_REPLANNED) == 0


@pytest.mark.story("SCRUM-50")
def test_a_closure_tells_attendees_once_without_a_second_coordinator_alert(
    db: Session, make_user: MakeUser
) -> None:
    event, booking, coordinator = _confirmed(db, make_user)
    attendee = _register(db, event, make_user)
    staff = make_user("venue_staff")
    fields = VenueUnavailabilityFields(
        starts_at=booking.start_at, ends_at=booking.end_at, reason="Burst pipe"
    )
    saved = closures.create(db, booking.venue_id, fields, staff.id, _NOW).record
    closures.update(db, booking.venue_id, saved.id, fields, staff.id, _NOW + _H)

    assert _got(db, attendee.id, NotificationType.EVENT_REPLANNED) == 1
    assert _got(db, coordinator.id, NotificationType.EVENT_REPLANNED) == 0
    assert _got(db, coordinator.id, NotificationType.VENUE_CLOSURE_IMPACT) == 1


# --------------------------------------------------------------------------- AC7


@pytest.mark.story("SCRUM-50")
def test_completion_notifies_the_organiser_and_coordinator_once(
    db: Session, make_user: MakeUser
) -> None:
    event, _, coordinator = _confirmed(db, make_user)
    assert event.end_at is not None

    event_completions.complete(db, event.id, coordinator.id, None, None, event.end_at)
    with pytest.raises(event_completions.NotCompletableError):
        event_completions.complete(db, event.id, coordinator.id, None, None, event.end_at)

    assert _got(db, event.organiser_id, NotificationType.EVENT_COMPLETED) == 1
    assert _got(db, coordinator.id, NotificationType.EVENT_COMPLETED) == 1
