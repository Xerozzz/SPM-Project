"""SCRUM-42 evidence for attendee submission and private registration status."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from domain.registration import RegistrationStatus
from models.event_registration import EventRegistration, EventRegistrationHistory
from models.event_request import EventRequest
from repositories import event_registrations as repo
from services import registration_intake
from tests.integration.test_registration_intake import confirmed_event
from tests.integration.test_submit_event_request import MakeClient, MakeUser


def open_event(db: Session, make_user: MakeUser) -> tuple[EventRequest, object]:
    event, organiser, _ = confirmed_event(db, make_user)
    registration_intake.open_intake(db, event.id, None, datetime.now(UTC))
    return event, organiser


def submission(overrides: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "full_name": "Ada Lovelace",
        "age": 24,
        "phone_number": "+65 8123 4567",
        "dietary_accessibility_notes": "Vegetarian meal, step-free access.",
        **(overrides or {}),
    }


@pytest.mark.story("SCRUM-42")
async def test_attendee_can_view_open_event_and_create_one_pending_registration(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = open_event(db, make_user)
    attendee = make_user("attendee")

    async with make_client(attendee) as client:
        listed = await client.get("/api/attendee/events")
        created = await client.post(
            f"/api/attendee/events/{event.id}/registrations", json=submission()
        )

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
    assert registration.full_name == "Ada Lovelace"
    assert registration.age == 24
    assert registration.phone_number == "+65 8123 4567"
    assert registration.dietary_accessibility_notes == "Vegetarian meal, step-free access."
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
        anonymous = await client.post(
            f"/api/attendee/events/{event.id}/registrations", json=submission()
        )
    async with make_client(organiser) as client:
        forbidden = await client.post(
            f"/api/attendee/events/{event.id}/registrations", json=submission()
        )

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
        refused = await client.post(
            f"/api/attendee/events/{event.id}/registrations", json=submission()
        )

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
        refused = await client.post(
            f"/api/attendee/events/{event.id}/registrations", json=submission()
        )

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
        first = await client.post(
            f"/api/attendee/events/{event.id}/registrations", json=submission()
        )
        retry = await client.post(
            f"/api/attendee/events/{event.id}/registrations", json=submission()
        )

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
        created = await client.post(
            f"/api/attendee/events/{event.id}/registrations", json=submission()
        )
    registration_intake.close_intake(db, event.id, datetime.now(UTC))

    async with make_client(attendee) as client:
        mine = await client.get(f"/api/attendee/events/{event.id}/registration")
    async with make_client(other) as client:
        theirs = await client.get(f"/api/attendee/events/{event.id}/registration")

    assert mine.status_code == 200
    assert mine.json()["id"] == created.json()["id"]
    assert theirs.status_code == 404


@pytest.mark.story("SCRUM-115")
@pytest.mark.parametrize(
    "registration_status",
    [RegistrationStatus.PENDING, RegistrationStatus.WAITLISTED, RegistrationStatus.ACCEPTED],
)
async def test_attendee_can_withdraw_each_live_registration_state(
    db: Session,
    make_user: MakeUser,
    make_client: MakeClient,
    registration_status: RegistrationStatus,
) -> None:
    event, _ = open_event(db, make_user)
    attendee = make_user("attendee")
    async with make_client(attendee) as client:
        created = await client.post(
            f"/api/attendee/events/{event.id}/registrations", json=submission()
        )
    registration = db.get(EventRegistration, created.json()["id"])
    assert registration is not None
    registration.status = registration_status
    db.commit()

    async with make_client(attendee) as client:
        withdrawn = await client.post(f"/api/attendee/events/{event.id}/registration/withdraw")

    assert withdrawn.status_code == 200
    assert withdrawn.json()["status"] == "withdrawn"
    assert withdrawn.json()["already_withdrawn"] is False
    history = db.scalars(
        select(EventRegistrationHistory)
        .where(EventRegistrationHistory.registration_id == registration.id)
        .order_by(EventRegistrationHistory.occurred_at)
    ).all()
    withdrawal = history[-1]
    assert withdrawal.actor_id == attendee.id
    assert withdrawal.previous_status is registration_status
    assert withdrawal.status is RegistrationStatus.WITHDRAWN
    assert withdrawal.occurred_at.tzinfo is not None


@pytest.mark.story("SCRUM-115")
async def test_attendee_cannot_withdraw_another_attendees_registration(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = open_event(db, make_user)
    attendee = make_user("attendee")
    other = make_user("attendee")
    async with make_client(attendee) as client:
        created = await client.post(
            f"/api/attendee/events/{event.id}/registrations", json=submission()
        )
    async with make_client(other) as client:
        refused = await client.post(f"/api/attendee/events/{event.id}/registration/withdraw")

    assert refused.status_code == 404
    registration = db.get(EventRegistration, created.json()["id"])
    assert registration is not None and registration.status is RegistrationStatus.PENDING


@pytest.mark.story("SCRUM-115")
async def test_withdrawal_is_allowed_after_intake_closes_but_not_after_event_leaves_active_state(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = open_event(db, make_user)
    attendee = make_user("attendee")
    async with make_client(attendee) as client:
        created = await client.post(
            f"/api/attendee/events/{event.id}/registrations", json=submission()
        )
    registration_intake.close_intake(db, event.id, datetime.now(UTC))
    async with make_client(attendee) as client:
        closed_intake = await client.post(f"/api/attendee/events/{event.id}/registration/withdraw")

    assert closed_intake.status_code == 200
    event.status = EventStatus.APPROVED
    db.commit()
    async with make_client(attendee) as client:
        inactive = await client.post(f"/api/attendee/events/{event.id}/registration/withdraw")

    assert inactive.status_code == 409
    assert db.get(EventRegistration, created.json()["id"]).status is RegistrationStatus.WITHDRAWN


@pytest.mark.story("SCRUM-115")
async def test_repeated_withdrawal_is_idempotent_and_does_not_duplicate_history(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = open_event(db, make_user)
    attendee = make_user("attendee")
    async with make_client(attendee) as client:
        created = await client.post(
            f"/api/attendee/events/{event.id}/registrations", json=submission()
        )
        first = await client.post(f"/api/attendee/events/{event.id}/registration/withdraw")
        repeated = await client.post(f"/api/attendee/events/{event.id}/registration/withdraw")

    assert first.status_code == 200
    assert repeated.status_code == 200
    assert repeated.json()["already_withdrawn"] is True
    assert (
        db.scalar(
            select(func.count())
            .select_from(EventRegistrationHistory)
            .where(EventRegistrationHistory.registration_id == created.json()["id"])
        )
        == 2
    )


@pytest.mark.story("SCRUM-115")
async def test_attendee_can_reregister_after_withdrawal_with_new_submission_priority(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = open_event(db, make_user)
    attendee = make_user("attendee")
    async with make_client(attendee) as client:
        original = await client.post(
            f"/api/attendee/events/{event.id}/registrations", json=submission()
        )
        await client.post(f"/api/attendee/events/{event.id}/registration/withdraw")
        replacement = await client.post(
            f"/api/attendee/events/{event.id}/registrations", json=submission({"age": 25})
        )
        current = await client.get(f"/api/attendee/events/{event.id}/registration")

    assert replacement.status_code == 201
    assert replacement.json()["status"] == "pending"
    assert replacement.json()["id"] != original.json()["id"]
    assert replacement.json()["submission_order"] > original.json()["submission_order"]
    assert datetime.fromisoformat(replacement.json()["submitted_at"]) >= datetime.fromisoformat(
        original.json()["submitted_at"]
    )
    assert current.json()["id"] == replacement.json()["id"]
    original_record = db.get(EventRegistration, original.json()["id"])
    assert original_record is not None and original_record.status is RegistrationStatus.WITHDRAWN
    assert len(repo.list_history(db, original_record.id)) == 2


@pytest.mark.story("SCRUM-115")
@pytest.mark.parametrize("state", ["closed", "suspended", "expired"])
async def test_reregistration_reuses_intake_refusals(
    db: Session, make_user: MakeUser, make_client: MakeClient, state: str
) -> None:
    event, _ = open_event(db, make_user)
    attendee = make_user("attendee")
    async with make_client(attendee) as client:
        await client.post(f"/api/attendee/events/{event.id}/registrations", json=submission())
        await client.post(f"/api/attendee/events/{event.id}/registration/withdraw")
    now = datetime.now(UTC)
    if state == "closed":
        registration_intake.close_intake(db, event.id, now)
    elif state == "suspended":
        registration_intake.suspend_intake(db, event.id, now)
    else:
        event.registration_closes_at = now - timedelta(seconds=1)
        db.commit()

    async with make_client(attendee) as client:
        refused = await client.post(
            f"/api/attendee/events/{event.id}/registrations", json=submission()
        )

    assert refused.status_code == 409
    assert db.scalar(select(func.count()).select_from(EventRegistration)) == 1


@pytest.mark.story("SCRUM-42")
async def test_invalid_required_information_creates_no_registration(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = open_event(db, make_user)
    attendee = make_user("attendee")
    invalid = submission({"full_name": " ", "age": -1, "phone_number": ""})

    async with make_client(attendee) as client:
        refused = await client.post(f"/api/attendee/events/{event.id}/registrations", json=invalid)

    assert refused.status_code == 422
    fields = {problem["loc"][-1] for problem in refused.json()["detail"]}
    assert fields == {"full_name", "age", "phone_number"}
    assert db.scalar(select(func.count()).select_from(EventRegistration)) == 0


@pytest.mark.story("SCRUM-42")
def test_registration_status_vocabulary_supports_downstream_decisions() -> None:
    assert {status.value for status in RegistrationStatus} == {
        "pending",
        "waitlisted",
        "accepted",
        "withdrawn",
        "cancelled",
    }
