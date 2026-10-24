"""SCRUM-134 evidence for Organiser-managed registration outcomes."""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from domain.registration import RegistrationStatus
from models.event_registration import EventRegistration
from repositories import event_registrations as registrations
from services import event_registrations, registration_intake
from tests.integration.test_registration_intake import confirmed_event
from tests.integration.test_submit_event_request import MakeClient, MakeUser


def registration(
    db: Session,
    event_id: uuid.UUID,
    attendee_id: uuid.UUID,
    status: RegistrationStatus = RegistrationStatus.PENDING,
) -> EventRegistration:
    row = registrations.add_submission(
        db,
        event_id,
        attendee_id,
        datetime(2020, 1, 1, tzinfo=UTC),
        1,
        "Ada Lovelace",
        24,
        "+65 8123 4567",
        None,
    )
    row.status = status
    db.commit()
    return row


async def decide(
    client: AsyncClient,
    event_id: uuid.UUID,
    row: EventRegistration,
    target: str,
    note: str | None = None,
    expected: str | None = None,
) -> Response:
    return await client.post(
        f"/api/event-requests/{event_id}/registrations/{row.id}/decision",
        json={"expected_status": expected or row.status.value, "status": target, "note": note},
    )


@pytest.mark.story("SCRUM-134")
@pytest.mark.parametrize(
    ("current", "target"),
    [
        (RegistrationStatus.PENDING, "accepted"),
        (RegistrationStatus.WAITLISTED, "accepted"),
        (RegistrationStatus.PENDING, "waitlisted"),
        (RegistrationStatus.ACCEPTED, "waitlisted"),
    ],
)
async def test_owner_records_each_permitted_manual_outcome(
    db: Session,
    make_user: MakeUser,
    make_client: MakeClient,
    current: RegistrationStatus,
    target: str,
) -> None:
    event, organiser, _ = confirmed_event(db, make_user)
    row = registration(db, event.id, make_user("attendee").id, current)

    async with make_client(organiser) as client:
        response = await decide(client, event.id, row, target, "Reviewed in submission order")

    assert response.status_code == 200
    assert response.json()["status"] == target
    history = registrations.list_history(db, row.id)
    assert len(history) == 2
    action = next(item for item in history if item.note == "Reviewed in submission order")
    assert action.actor_id == organiser.id
    assert action.previous_status is current
    assert action.status.value == target
    assert action.note == "Reviewed in submission order"
    assert action.occurred_at.tzinfo is not None


@pytest.mark.story("SCRUM-134")
async def test_only_owner_can_record_a_decision_and_list_access_is_unchanged(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, coordinator = confirmed_event(db, make_user)
    row = registration(db, event.id, make_user("attendee").id)
    others = [coordinator, make_user("organiser"), make_user("attendee"), None]

    outcomes = []
    for user in others:
        async with make_client(user) as client:
            outcomes.append((await decide(client, event.id, row, "accepted")).status_code)
    async with make_client(organiser) as client:
        listed = await client.get(f"/api/event-requests/{event.id}/registrations")

    assert outcomes == [403, 403, 403, 401]
    assert listed.status_code == 200
    stored = db.get(EventRegistration, row.id)
    assert stored is not None and stored.status is RegistrationStatus.PENDING


@pytest.mark.story("SCRUM-134")
async def test_decision_preserves_history_submission_order_and_attendee_status_view(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, _ = confirmed_event(db, make_user)
    attendee = make_user("attendee")
    row = registration(db, event.id, attendee.id)
    original = (row.submitted_at, row.submission_order)

    async with make_client(organiser) as client:
        changed = await decide(client, event.id, row, "accepted")
    async with make_client(attendee) as client:
        mine = await client.get(f"/api/attendee/events/{event.id}/registration")

    assert changed.status_code == mine.status_code == 200
    stored = db.get(EventRegistration, row.id)
    assert stored is not None and (stored.submitted_at, stored.submission_order) == original
    assert mine.json()["id"] == str(row.id)
    assert mine.json()["status"] == "accepted"


@pytest.mark.story("SCRUM-134")
async def test_stale_and_concurrent_withdrawal_decisions_are_refused_without_new_actions(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, _ = confirmed_event(db, make_user)
    attendee = make_user("attendee")
    row = registration(db, event.id, attendee.id)
    now = datetime.now(UTC)
    event_registrations.withdraw(db, event.id, attendee.id, now)

    async with make_client(organiser) as client:
        stale = await decide(client, event.id, row, "accepted")

    assert stale.status_code == 409
    stored = db.get(EventRegistration, row.id)
    assert stored is not None and stored.status is RegistrationStatus.WITHDRAWN
    assert len(registrations.list_history(db, row.id)) == 2


@pytest.mark.story("SCRUM-134")
async def test_exact_retry_is_idempotent_but_another_action_is_stale(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, _ = confirmed_event(db, make_user)
    row = registration(db, event.id, make_user("attendee").id)
    async with make_client(organiser) as client:
        first = await decide(client, event.id, row, "accepted", "Room available")
        repeated = await decide(
            client, event.id, row, "accepted", "Room available", expected="pending"
        )
        stale = await decide(
            client, event.id, row, "accepted", "Different note", expected="pending"
        )

    assert first.status_code == repeated.status_code == 200
    assert repeated.json()["already_decided"] is True
    assert stale.status_code == 409
    assert len(registrations.list_history(db, row.id)) == 2


@pytest.mark.story("SCRUM-134")
@pytest.mark.parametrize("state", [RegistrationStatus.WITHDRAWN, RegistrationStatus.CANCELLED])
async def test_terminal_registration_states_cannot_be_decided(
    db: Session, make_user: MakeUser, make_client: MakeClient, state: RegistrationStatus
) -> None:
    event, organiser, _ = confirmed_event(db, make_user)
    row = registration(db, event.id, make_user("attendee").id, state)
    before = len(registrations.list_history(db, row.id))
    async with make_client(organiser) as client:
        refused = await decide(client, event.id, row, "accepted")

    assert refused.status_code == 409
    assert len(registrations.list_history(db, row.id)) == before


@pytest.mark.story("SCRUM-134")
async def test_closed_intake_allows_decisions_but_replanning_requires_reconfirmation(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, _ = confirmed_event(db, make_user)
    row = registration(db, event.id, make_user("attendee").id)
    registration_intake.open_intake(db, event.id, None, datetime.now(UTC))
    registration_intake.close_intake(db, event.id, datetime.now(UTC))
    async with make_client(organiser) as client:
        closed = await decide(client, event.id, row, "accepted")
    replanning_row = registrations.add_submission(
        db,
        event.id,
        make_user("attendee").id,
        datetime(2020, 1, 2, tzinfo=UTC),
        2,
        "Grace Hopper",
        25,
        "+65 8123 4567",
        None,
    )
    event.status = EventStatus.APPROVED
    event.registration_suspended_at = datetime.now(UTC)
    db.commit()
    async with make_client(organiser) as client:
        suspended = await decide(client, event.id, replanning_row, "accepted")
    event.status = EventStatus.CONFIRMED
    db.commit()
    async with make_client(organiser) as client:
        reconfirmed = await decide(client, event.id, replanning_row, "accepted")

    assert closed.status_code == reconfirmed.status_code == 200
    assert suspended.status_code == 409


@pytest.mark.story("SCRUM-134")
async def test_decisions_do_not_allocate_or_promote_other_registrations(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, _ = confirmed_event(db, make_user)
    event.expected_attendance = 0
    first = registration(db, event.id, make_user("attendee").id)
    second = registrations.add_submission(
        db,
        event.id,
        make_user("attendee").id,
        datetime(2030, 1, 2, tzinfo=UTC),
        2,
        "Grace",
        25,
        "+65",
        None,
    )
    second.status = RegistrationStatus.WAITLISTED
    db.commit()
    async with make_client(organiser) as client:
        changed = await decide(client, event.id, first, "accepted")

    assert changed.status_code == 200
    stored = db.get(EventRegistration, second.id)
    assert stored is not None and stored.status is RegistrationStatus.WAITLISTED
