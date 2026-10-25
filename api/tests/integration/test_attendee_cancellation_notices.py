"""SCRUM-135: attendees are told when an event they registered for is cancelled.

The notice is staged by SCRUM-115's cancellation in its own transaction, to each attendee
whose Pending, Waitlisted or Accepted registration it cancelled, under the same key as the
staff notices for that cancellation.
"""

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.notifications import NotificationSource, NotificationType
from domain.registration import RegistrationStatus
from models.event_request import EventRequest
from models.notification import Notification
from models.user import User
from repositories import equipment_reservations as reservation_repo
from repositories import event_registrations as registration_repo
from services import event_cancellations as service
from services import event_registrations
from tests.integration.test_cancel_event import _confirmed, _got, _register, _url
from tests.integration.test_safety_review import _NOW
from tests.integration.test_submit_event_request import MakeClient, MakeUser


def _open(db: Session, event: EventRequest) -> None:
    event.registration_opened_at = _NOW
    db.flush()


@pytest.mark.story("SCRUM-135")
def test_each_live_attendee_is_told_once_and_withdrawn_ones_are_not(
    db: Session, make_user: MakeUser
) -> None:
    event, _, coordinator = _confirmed(db, make_user)
    _open(db, event)
    pending = _register(db, event, make_user)
    accepted = _register(db, event, make_user)
    waitlisted = _register(db, event, make_user)
    withdrawn = _register(db, event, make_user)
    decided = _NOW + timedelta(minutes=1)
    registration_repo.decide(
        db, accepted, event.organiser_id, RegistrationStatus.ACCEPTED, decided, None
    )
    registration_repo.decide(
        db, waitlisted, event.organiser_id, RegistrationStatus.WAITLISTED, decided, None
    )
    event_registrations.withdraw(db, event.id, withdrawn.attendee_id, decided)
    bystander = make_user("attendee")

    service.cancel(db, event.id, coordinator.id, "Storm warning", None, _NOW + timedelta(hours=1))

    for registration in (pending, accepted, waitlisted):
        assert _got(db, registration.attendee_id, NotificationType.EVENT_CANCELLED) == 1
    assert _got(db, withdrawn.attendee_id, NotificationType.EVENT_CANCELLED) == 0
    assert _got(db, bystander.id, NotificationType.EVENT_CANCELLED) == 0


@pytest.mark.story("SCRUM-135")
def test_the_notice_is_keyed_to_the_same_cancellation_as_the_staff_notices(
    db: Session, make_user: MakeUser
) -> None:
    event, _, coordinator = _confirmed(db, make_user)
    _open(db, event)
    attendee = _register(db, event, make_user).attendee_id

    service.cancel(db, event.id, coordinator.id, "Storm warning", None, _NOW)

    db.expire_all()
    keys = {
        (row.source_type, row.source_id)
        for row in db.scalars(
            select(Notification).where(
                Notification.event_request_id == event.id,
                Notification.type == NotificationType.EVENT_CANCELLED.value,
            )
        )
    }
    assert keys == {(NotificationSource.EVENT_CANCELLATION.value, str(event.id))}
    assert _got(db, attendee, NotificationType.EVENT_CANCELLED) == 1


@pytest.mark.story("SCRUM-135")
def test_an_attendee_who_also_runs_the_event_is_told_once(db: Session, make_user: MakeUser) -> None:
    event, _, coordinator = _confirmed(db, make_user)
    _open(db, event)
    event_registrations.submit(
        db, event.id, event.organiser_id, "Owner Too", 30, "+65 8000 0000", None, _NOW
    )

    service.cancel(db, event.id, coordinator.id, "Storm warning", None, _NOW)

    assert _got(db, event.organiser_id, NotificationType.EVENT_CANCELLED) == 1


@pytest.mark.story("SCRUM-135")
def test_a_repeat_tells_nobody_again(db: Session, make_user: MakeUser) -> None:
    event, _, coordinator = _confirmed(db, make_user)
    _open(db, event)
    attendee = _register(db, event, make_user).attendee_id
    service.cancel(db, event.id, coordinator.id, "Storm warning", None, _NOW)

    with pytest.raises(service.NotCancellableError):
        service.cancel(db, event.id, coordinator.id, "Again", None, _NOW + timedelta(hours=1))
    db.rollback()

    assert _got(db, attendee, NotificationType.EVENT_CANCELLED) == 1


@pytest.mark.story("SCRUM-135")
def test_a_rolled_back_cancellation_tells_no_attendee(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    event, _, coordinator = _confirmed(db, make_user)
    _open(db, event)
    attendee = _register(db, event, make_user).attendee_id
    db.commit()

    def broken(*_: object) -> None:
        raise RuntimeError("database went away")

    monkeypatch.setattr(reservation_repo, "release_for_event", broken)
    with pytest.raises(RuntimeError):
        service.cancel(db, event.id, coordinator.id, "Storm warning", None, _NOW)
    db.rollback()
    monkeypatch.undo()

    assert _got(db, attendee, NotificationType.EVENT_CANCELLED) == 0


@pytest.mark.story("SCRUM-135")
async def test_a_refused_cancellation_tells_no_attendee(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, _ = _confirmed(db, make_user)
    _open(db, event)
    attendee = _register(db, event, make_user).attendee_id
    organiser = db.get(User, event.organiser_id)

    async with make_client(organiser) as client:
        response = await client.post(_url(event, "cancel"), json={"reason": "Not mine to do"})

    assert response.status_code == 403
    assert _got(db, attendee, NotificationType.EVENT_CANCELLED) == 0
