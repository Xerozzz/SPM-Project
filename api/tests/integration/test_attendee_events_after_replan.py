"""SCRUM-42: an attendee keeps seeing their registration when the event leaves Confirmed."""

import pytest
from sqlalchemy.orm import Session

from domain.change_decision import Decision
from domain.event_status import EventStatus
from models.event_request import EventRequest
from models.user import User
from services import event_registrations
from tests.integration.test_intake_suspension_on_replan import _open
from tests.integration.test_safety_approval_invalidation import _decide, _session_change
from tests.integration.test_safety_review import _NOW
from tests.integration.test_submit_event_request import MakeClient, MakeUser


def _registered(db: Session, make_user: MakeUser) -> tuple[EventRequest, User]:
    event, booking, coordinator = _open(db, make_user)
    attendee = make_user("attendee")
    event_registrations.submit(
        db, event.id, attendee.id, "Ada Lovelace", 24, "+65 8123 4567", None, _NOW
    )
    _decide(db, event, _session_change(db, event, booking), coordinator, Decision.APPROVE)
    return event, attendee


@pytest.mark.story("SCRUM-42")
async def test_registered_attendee_still_sees_an_event_that_is_being_replanned(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, attendee = _registered(db, make_user)
    assert event.status == EventStatus.APPROVED

    async with make_client(attendee) as client:
        listed = await client.get("/api/attendee/events")
        mine = await client.get(f"/api/attendee/events/{event.id}/registration")

    [visible] = listed.json()
    assert visible["id"] == str(event.id)
    assert visible["status"] == "approved"
    assert visible["intake_open"] is False
    assert mine.status_code == 200
    assert mine.json()["status"] == "pending"


@pytest.mark.story("SCRUM-42")
async def test_attendee_without_a_registration_does_not_see_a_replanned_event(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    _registered(db, make_user)

    async with make_client(make_user("attendee")) as client:
        listed = await client.get("/api/attendee/events")

    assert listed.json() == []


@pytest.mark.story("SCRUM-42")
@pytest.mark.parametrize("final", [EventStatus.CANCELLED, EventStatus.COMPLETED])
async def test_registered_attendee_still_sees_a_cancelled_or_completed_event(
    db: Session, make_user: MakeUser, make_client: MakeClient, final: EventStatus
) -> None:
    event, attendee = _registered(db, make_user)
    event.status = final
    db.flush()

    async with make_client(attendee) as client:
        listed = await client.get("/api/attendee/events")

    [visible] = listed.json()
    assert visible["status"] == final.value
    assert visible["intake_open"] is False
