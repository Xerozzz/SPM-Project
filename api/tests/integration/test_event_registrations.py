"""SCRUM-42 evidence for attendee submission and private registration status."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from domain.registration import RegistrationStatus
from models.event_registration import EventRegistration, EventRegistrationHistory
from models.event_request import EventRequest
from services import registration_intake
from tests.integration.test_registration_intake import confirmed_event
from tests.integration.test_submit_event_request import MakeClient, MakeUser


def open_event(db: Session, make_user: MakeUser) -> tuple[EventRequest, object]:
    event, organiser, _ = confirmed_event(db, make_user)
    registration_intake.open_intake(db, event.id, None, datetime.now(UTC))
    return event, organiser


@pytest.mark.story("SCRUM-42")
async def test_attendee_can_view_open_event_and_create_one_pending_registration(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = open_event(db, make_user)
    attendee = make_user("attendee")

    async with make_client(attendee) as client:
        listed = await client.get("/api/attendee/events")
        created = await client.post(f"/api/attendee/events/{event.id}/registrations")

    assert listed.status_code == 200
    [visible] = listed.json()
    assert visible["id"] == str(event.id)
    assert visible["name"] == event.name
    assert visible["description"] == event.description
    assert datetime.fromisoformat(visible["start_at"]) == event.start_at
    assert datetime.fromisoformat(visible["end_at"]) == event.end_at
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "pending"
    assert body["event_request_id"] == str(event.id)
    assert body["submission_order"] == 1
    assert datetime.fromisoformat(body["submitted_at"]).tzinfo is not None
    registration = db.get(EventRegistration, body["id"])
    assert registration is not None and registration.attendee_id == attendee.id
    assert registration.status is RegistrationStatus.PENDING
    assert (
        db.scalar(
            select(func.count())
            .select_from(EventRegistrationHistory)
            .where(EventRegistrationHistory.registration_id == registration.id)
        )
        == 1
    )


@pytest.mark.story("SCRUM-42")
async def test_only_an_authenticated_attendee_can_view_or_submit(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = open_event(db, make_user)
    organiser = make_user("organiser")

    async with make_client(None) as client:
        anonymous = await client.post(f"/api/attendee/events/{event.id}/registrations")
    async with make_client(organiser) as client:
        forbidden = await client.post(f"/api/attendee/events/{event.id}/registrations")

    assert anonymous.status_code == 401
    assert forbidden.status_code == 403
    assert db.scalar(select(func.count()).select_from(EventRegistration)) == 0


@pytest.mark.story("SCRUM-42")
@pytest.mark.parametrize("state", ["closed", "suspended", "expired"])
async def test_closed_suspended_or_expired_intake_creates_no_registration(
    db: Session, make_user: MakeUser, make_client: MakeClient, state: str
) -> None:
    event, _ = open_event(db, make_user)
    attendee = make_user("attendee")
    now = datetime.now(UTC)
    if state == "closed":
        registration_intake.close_intake(db, event.id, now)
    elif state == "suspended":
        registration_intake.suspend_intake(db, event.id, now)
    else:
        event.registration_closes_at = now - timedelta(seconds=1)
        db.commit()

    async with make_client(attendee) as client:
        refused = await client.post(f"/api/attendee/events/{event.id}/registrations")

    assert refused.status_code == 409
    assert db.scalar(select(func.count()).select_from(EventRegistration)) == 0


@pytest.mark.story("SCRUM-42")
async def test_non_confirmed_event_cannot_receive_a_registration(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = open_event(db, make_user)
    attendee = make_user("attendee")
    event.status = EventStatus.APPROVED
    db.commit()

    async with make_client(attendee) as client:
        refused = await client.post(f"/api/attendee/events/{event.id}/registrations")

    assert refused.status_code == 409
    assert db.scalar(select(func.count()).select_from(EventRegistration)) == 0


@pytest.mark.story("SCRUM-42")
async def test_retry_is_a_conflict_with_no_second_record_history_or_capacity_decision(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = open_event(db, make_user)
    event.expected_attendance = 0
    db.commit()
    attendee = make_user("attendee")

    async with make_client(attendee) as client:
        first = await client.post(f"/api/attendee/events/{event.id}/registrations")
        retry = await client.post(f"/api/attendee/events/{event.id}/registrations")

    assert first.status_code == 201
    assert retry.status_code == 409
    assert retry.json()["detail"]["id"] == first.json()["id"]
    assert db.scalar(select(func.count()).select_from(EventRegistration)) == 1
    assert db.scalar(select(func.count()).select_from(EventRegistrationHistory)) == 1
    assert db.scalar(select(EventRegistration.status)) is RegistrationStatus.PENDING


@pytest.mark.story("SCRUM-42")
async def test_attendee_can_read_only_their_registration_after_intake_closes(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = open_event(db, make_user)
    attendee = make_user("attendee")
    other = make_user("attendee")
    async with make_client(attendee) as client:
        created = await client.post(f"/api/attendee/events/{event.id}/registrations")
    registration_intake.close_intake(db, event.id, datetime.now(UTC))

    async with make_client(attendee) as client:
        mine = await client.get(f"/api/attendee/events/{event.id}/registration")
    async with make_client(other) as client:
        theirs = await client.get(f"/api/attendee/events/{event.id}/registration")

    assert mine.status_code == 200
    assert mine.json()["id"] == created.json()["id"]
    assert theirs.status_code == 404


@pytest.mark.story("SCRUM-42")
def test_registration_status_vocabulary_supports_downstream_decisions() -> None:
    assert {status.value for status in RegistrationStatus} == {
        "pending",
        "waitlisted",
        "accepted",
        "withdrawn",
        "cancelled",
    }
