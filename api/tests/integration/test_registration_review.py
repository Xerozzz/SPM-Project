"""SCRUM-114 evidence for the read-only registration review list."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.registration import RegistrationStatus
from models.event_registration import EventRegistration, EventRegistrationHistory
from models.event_request import EventRequest
from repositories import event_registrations as registrations
from services import registration_intake
from tests.integration.test_registration_intake import confirmed_event
from tests.integration.test_submit_event_request import MakeClient, MakeUser


def registration(
    db: Session,
    event: EventRequest,
    attendee_id: uuid.UUID,
    submitted_at: datetime,
    submission_order: int,
    *,
    name: str,
) -> EventRegistration:
    return registrations.add_submission(
        db,
        event.id,
        attendee_id,
        submitted_at,
        submission_order,
        name,
        20,
        "+65 8123 4567",
        "Step-free access.",
    )


@pytest.mark.story("SCRUM-114")
async def test_owner_and_assigned_coordinator_view_every_registration_in_submission_order(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, coordinator = confirmed_event(db, make_user)
    first_attendee = make_user("attendee")
    second_attendee = make_user("attendee")
    moment = datetime(2030, 1, 1, tzinfo=UTC)
    later = registration(
        db, event, second_attendee.id, moment + timedelta(seconds=1), 2, name="Later"
    )
    first = registration(db, event, first_attendee.id, moment, 1, name="First")
    db.commit()

    async with make_client(organiser) as client:
        owner_response = await client.get(f"/api/event-requests/{event.id}/registrations")
    async with make_client(coordinator) as client:
        coordinator_response = await client.get(f"/api/event-requests/{event.id}/registrations")

    assert owner_response.status_code == coordinator_response.status_code == 200
    assert [row["id"] for row in owner_response.json()] == [str(first.id), str(later.id)]
    assert owner_response.json() == coordinator_response.json()
    assert owner_response.json()[0]["full_name"] == "First"
    assert owner_response.json()[0]["dietary_accessibility_notes"] == "Step-free access."


@pytest.mark.story("SCRUM-114")
async def test_review_refuses_non_owner_unassigned_coordinator_attendee_and_anonymous_users(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, _ = confirmed_event(db, make_user)
    users = [make_user("organiser"), make_user("coordinator"), make_user("attendee"), None]

    statuses = []
    for user in users:
        async with make_client(user) as client:
            response = await client.get(f"/api/event-requests/{event.id}/registrations")
            statuses.append(response.status_code)

    assert statuses == [403, 403, 403, 401]


@pytest.mark.story("SCRUM-114")
async def test_review_uses_submission_order_for_timestamp_ties_and_keeps_statuses_unchanged(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, _ = confirmed_event(db, make_user)
    first_attendee = make_user("attendee")
    second_attendee = make_user("attendee")
    moment = datetime(2030, 1, 1, tzinfo=UTC)
    second = registration(db, event, second_attendee.id, moment, 2, name="Second")
    first = registration(db, event, first_attendee.id, moment, 1, name="First")
    first.status = RegistrationStatus.ACCEPTED
    second.status = RegistrationStatus.WAITLISTED
    db.commit()

    async with make_client(organiser) as client:
        response = await client.get(f"/api/event-requests/{event.id}/registrations")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [str(first.id), str(second.id)]
    assert [row["status"] for row in response.json()] == ["accepted", "waitlisted"]


@pytest.mark.story("SCRUM-114")
async def test_reregistered_attendee_has_a_new_position_and_review_does_not_write_history(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, _ = confirmed_event(db, make_user)
    attendee = make_user("attendee")
    another = make_user("attendee")
    moment = datetime(2030, 1, 1, tzinfo=UTC)
    original = registration(db, event, attendee.id, moment, 1, name="Original")
    registrations.withdraw(db, original, attendee.id, moment + timedelta(minutes=1))
    retained = registration(
        db, event, another.id, moment + timedelta(minutes=2), 2, name="Retained"
    )
    retained.status = RegistrationStatus.WAITLISTED
    replacement = registration(
        db, event, attendee.id, moment + timedelta(minutes=3), 3, name="Replacement"
    )
    db.commit()
    before = [
        (row.id, row.status, row.submitted_at, row.submission_order)
        for row in db.scalars(
            select(EventRegistration).order_by(EventRegistration.submission_order)
        )
    ]
    history_count = len(db.scalars(select(EventRegistrationHistory)).all())

    async with make_client(organiser) as client:
        response = await client.get(f"/api/event-requests/{event.id}/registrations")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [
        str(original.id),
        str(retained.id),
        str(replacement.id),
    ]
    assert [row["status"] for row in response.json()] == ["withdrawn", "waitlisted", "pending"]
    after = [
        (row.id, row.status, row.submitted_at, row.submission_order)
        for row in db.scalars(
            select(EventRegistration).order_by(EventRegistration.submission_order)
        )
    ]
    assert after == before
    assert len(db.scalars(select(EventRegistrationHistory)).all()) == history_count


@pytest.mark.story("SCRUM-114")
@pytest.mark.parametrize("closed_by", ["manual", "deadline"])
async def test_review_remains_visible_after_intake_closes(
    db: Session, make_user: MakeUser, make_client: MakeClient, closed_by: str
) -> None:
    event, organiser, _ = confirmed_event(db, make_user)
    attendee = make_user("attendee")
    created = registration(db, event, attendee.id, datetime(2030, 1, 1, tzinfo=UTC), 1, name="Ada")
    now = datetime.now(UTC)
    event.registration_opened_at = now - timedelta(hours=1)
    event.registration_closes_at = now - timedelta(seconds=1)
    db.commit()
    if closed_by == "manual":
        event.registration_closes_at = None
        db.commit()
        registration_intake.close_intake(db, event.id, now)

    async with make_client(organiser) as client:
        response = await client.get(f"/api/event-requests/{event.id}/registrations")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [str(created.id)]


@pytest.mark.story("SCRUM-114")
async def test_review_returns_an_empty_list_without_allocating_attendance(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, _ = confirmed_event(db, make_user)
    event.expected_attendance = 0
    db.commit()

    async with make_client(organiser) as client:
        response = await client.get(f"/api/event-requests/{event.id}/registrations")

    assert response.status_code == 200
    assert response.json() == []
