"""SCRUM-86: the assigned Coordinator completes an event and keeps its closure record."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from domain.event_status import EventStatus, InvalidTransitionError, replan
from domain.registration import RegistrationStatus
from domain.registration_intake import RegistrationIntakeError
from domain.roles import Role
from domain.venue_booking import BookingStatus
from models.event_closure_note import EventClosureNote
from models.event_registration import EventRegistration
from models.event_request import EventRequest
from models.user import User
from models.venue_booking import VenueBooking
from repositories import equipment as catalogue_repo
from repositories import event_closures as closure_repo
from repositories import safety_reviews as safety_repo
from services import event_completions as service
from services import event_confirmations, event_registrations
from services import registration_intake as intake_service
from tests.integration.test_event_confirmation import ready_event
from tests.integration.test_safety_review import _NOW
from tests.integration.test_submit_event_request import MakeClient, MakeUser

_H = timedelta(hours=1)


def _ended(db: Session, make_user: MakeUser) -> tuple[EventRequest, VenueBooking, User]:
    """A Confirmed event whose recorded end time has already passed."""
    event, booking, coordinator = ready_event(db, make_user)
    event_confirmations.confirm(db, event, coordinator.id, _NOW)
    now = datetime.now(UTC)
    event.start_at, event.end_at = now - 3 * _H, now - _H
    db.flush()
    return event, booking, coordinator


def _url(event: EventRequest, path: str) -> str:
    return f"/api/event-requests/{event.id}/{path}"


def _stored(db: Session, event: EventRequest) -> EventRequest:
    db.expire_all()
    row = db.get(EventRequest, event.id)
    assert row is not None
    return row


# --------------------------------------------------------------------------- AC1, AC2, AC3


@pytest.mark.story("SCRUM-86")
async def test_the_assigned_coordinator_completes_an_ended_event(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator = _ended(db, make_user)

    async with make_client(coordinator) as client:
        response = await client.post(
            _url(event, "complete"), json={"actual_attendance": 172, "notes": " Ran late. "}
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert body["completed_by_id"] == str(coordinator.id)
    assert body["completed_at"] is not None
    assert body["current"]["version"] == 1
    assert body["current"]["actual_attendance"] == 172
    assert body["current"]["notes"] == "Ran late."
    stored = _stored(db, event)
    assert stored.status is EventStatus.COMPLETED
    assert stored.completed_by_id == coordinator.id


@pytest.mark.story("SCRUM-86")
async def test_no_attendance_is_not_the_same_as_zero(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator = _ended(db, make_user)

    async with make_client(coordinator) as client:
        done = await client.post(_url(event, "complete"), json={})
        zero = await client.post(_url(event, "closure-notes"), json={"actual_attendance": 0})

    assert done.json()["current"]["actual_attendance"] is None
    assert zero.json()["actual_attendance"] == 0


@pytest.mark.story("SCRUM-86")
async def test_a_negative_attendance_is_refused_and_nothing_changes(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator = _ended(db, make_user)

    async with make_client(coordinator) as client:
        response = await client.post(_url(event, "complete"), json={"actual_attendance": -1})

    assert response.status_code == 422
    assert response.json()["detail"] == [
        {"field": "actual_attendance", "reason": "must be zero or more"}
    ]
    assert _stored(db, event).status is EventStatus.CONFIRMED


@pytest.mark.story("SCRUM-86")
async def test_an_event_that_has_not_ended_cannot_be_completed(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator = ready_event(db, make_user)
    event_confirmations.confirm(db, event, coordinator.id, _NOW)

    async with make_client(coordinator) as client:
        response = await client.post(_url(event, "complete"), json={})

    assert response.status_code == 409
    assert response.json()["detail"] == "This event has not ended yet"
    assert _stored(db, event).status is EventStatus.CONFIRMED


@pytest.mark.story("SCRUM-86")
async def test_only_a_confirmed_event_can_be_completed(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator = ready_event(db, make_user)
    now = datetime.now(UTC)
    event.start_at, event.end_at = now - 3 * _H, now - _H
    db.flush()

    async with make_client(coordinator) as client:
        response = await client.post(_url(event, "complete"), json={})

    assert response.status_code == 409
    assert response.json()["detail"] == "Only a confirmed event can be completed"


@pytest.mark.story("SCRUM-86")
async def test_only_the_current_assigned_coordinator_completes(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, outgoing = _ended(db, make_user)
    organiser = db.get(User, event.organiser_id)
    assert organiser is not None
    current = make_user("coordinator")
    event.coordinator_id = current.id
    db.flush()

    for user in (organiser, outgoing, make_user("coordinator"), make_user("coordinator_lead")):
        async with make_client(user) as client:
            response = await client.post(_url(event, "complete"), json={})
        assert response.status_code == 403
    async with make_client(current) as client:
        assert (await client.post(_url(event, "complete"), json={})).status_code == 200


# --------------------------------------------------------------------------- AC2, AC7


@pytest.mark.story("SCRUM-86")
def test_completion_closes_open_intake_and_keeps_registrations(
    db: Session, make_user: MakeUser
) -> None:
    event, booking, coordinator = ready_event(db, make_user)
    event_confirmations.confirm(db, event, coordinator.id, _NOW)
    event.registration_opened_at = _NOW
    db.flush()
    attendee = make_user("attendee")
    registration = event_registrations.submit(
        db, event.id, attendee.id, "Ada Lovelace", 24, "+65 8123 4567", None, _NOW
    )
    assert event.end_at is not None
    after = event.end_at + _H

    service.complete(db, event.id, coordinator.id, 50, None, after)

    stored = _stored(db, event)
    assert stored.registration_closed_at == after
    with pytest.raises(RegistrationIntakeError):
        intake_service.require_open_intake(stored, after)
    kept = db.get(EventRegistration, registration.id)
    assert kept is not None and kept.status is RegistrationStatus.PENDING
    held = db.get(VenueBooking, booking.id)
    assert held is not None and held.status == BookingStatus.CONFIRMED


@pytest.mark.story("SCRUM-86")
def test_completion_without_open_intake_leaves_no_close_marker(
    db: Session, make_user: MakeUser
) -> None:
    event, _, coordinator = ready_event(db, make_user)
    event_confirmations.confirm(db, event, coordinator.id, _NOW)
    assert event.end_at is not None

    service.complete(db, event.id, coordinator.id, None, None, event.end_at)

    stored = _stored(db, event)
    assert stored.status is EventStatus.COMPLETED
    assert stored.registration_closed_at is None


@pytest.mark.story("SCRUM-86")
def test_elapsed_reservations_do_not_block_later_periods(db: Session, make_user: MakeUser) -> None:
    event, _, coordinator = ready_event(db, make_user)
    event_confirmations.confirm(db, event, coordinator.id, _NOW)
    assert event.start_at is not None and event.end_at is not None

    service.complete(db, event.id, coordinator.id, None, None, event.end_at)

    # The reservation is kept for its own window, and free for a later one.
    other = uuid.uuid4()
    window = catalogue_repo.reserved_quantity(db, "Projector", event.start_at, event.end_at, other)
    assert window == 1
    later = event.end_at + 24 * _H
    assert catalogue_repo.reserved_quantity(db, "Projector", later, later + _H, other) == 0


# --------------------------------------------------------------------------- AC5


@pytest.mark.story("SCRUM-86")
async def test_corrections_add_versions_and_keep_earlier_values(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator = _ended(db, make_user)

    async with make_client(coordinator) as client:
        await client.post(_url(event, "complete"), json={"actual_attendance": 120})
        fixed = await client.post(
            _url(event, "closure-notes"), json={"actual_attendance": 125, "notes": "Recounted"}
        )
        read = await client.get(_url(event, "closure"))

    assert fixed.status_code == 201
    assert fixed.json()["version"] == 2
    history = read.json()["history"]
    assert [(row["version"], row["actual_attendance"]) for row in history] == [(1, 120), (2, 125)]
    assert all(row["recorded_by_id"] == str(coordinator.id) for row in history)
    assert read.json()["current"]["notes"] == "Recounted"


@pytest.mark.story("SCRUM-86")
async def test_a_record_can_only_be_corrected_after_completion(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator = _ended(db, make_user)

    async with make_client(coordinator) as client:
        response = await client.post(_url(event, "closure-notes"), json={"notes": "Early"})

    assert response.status_code == 409
    assert closure_repo.notes_for_event(db, event.id) == []


# --------------------------------------------------------------------------- AC6


@pytest.mark.story("SCRUM-86")
async def test_completed_is_terminal_and_a_repeat_adds_nothing(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator = _ended(db, make_user)

    async with make_client(coordinator) as client:
        first = await client.post(_url(event, "complete"), json={"notes": "Done"})
        again = await client.post(_url(event, "complete"), json={"notes": "Again"})
        reconfirm = await client.post(_url(event, "confirm"))

    assert first.status_code == 200
    assert again.status_code == 409
    assert again.json()["detail"] == "This event is already completed"
    assert reconfirm.status_code == 409
    assert len(closure_repo.notes_for_event(db, event.id)) == 1
    with pytest.raises(InvalidTransitionError):
        replan(EventStatus.COMPLETED)


@pytest.mark.story("SCRUM-86")
def test_a_failure_leaves_the_event_confirmed_and_intake_open(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    event, _, coordinator = ready_event(db, make_user)
    event_confirmations.confirm(db, event, coordinator.id, _NOW)
    event.registration_opened_at = _NOW
    db.commit()
    assert event.end_at is not None

    def broken(*_: object) -> EventClosureNote:
        raise RuntimeError("database went away")

    monkeypatch.setattr(closure_repo, "add_note", broken)
    with pytest.raises(RuntimeError):
        service.complete(db, event.id, coordinator.id, None, None, event.end_at)
    db.rollback()
    monkeypatch.undo()

    stored = _stored(db, event)
    assert stored.status is EventStatus.CONFIRMED
    assert stored.registration_closed_at is None
    assert stored.completed_at is None


# --------------------------------------------------------------------------- AC4


@pytest.mark.story("SCRUM-86")
async def test_the_closure_record_is_for_the_people_involved(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, booking, coordinator = _ended(db, make_user)
    async with make_client(coordinator) as client:
        await client.post(_url(event, "complete"), json={"notes": "Smooth"})
    organiser = db.get(User, event.organiser_id)
    hold_staff = db.get(User, booking.held_by_id)
    officer_id = next(iter(_safety_officers(db, event)))
    officer = db.get(User, officer_id)
    assert organiser is not None and hold_staff is not None and officer is not None

    allowed = [organiser, coordinator, make_user("coordinator_lead"), hold_staff, officer]
    refused = [
        make_user("venue_staff"),
        make_user(Role.SAFETY_OFFICER.value),
        make_user("coordinator"),
        make_user("attendee"),
        make_user("organiser"),
    ]
    for user in allowed:
        async with make_client(user) as client:
            response = await client.get(_url(event, "closure"))
        assert response.status_code == 200, user.id
        assert set(response.json()) == {
            "event_request_id",
            "status",
            "completed_by_id",
            "completed_at",
            "current",
            "history",
        }
    for user in refused:
        async with make_client(user) as client:
            assert (await client.get(_url(event, "closure"))).status_code == 403


@pytest.mark.story("SCRUM-86")
async def test_an_outgoing_coordinator_loses_the_closure_record(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, outgoing = _ended(db, make_user)
    async with make_client(outgoing) as client:
        await client.post(_url(event, "complete"), json={})
    event.coordinator_id = make_user("coordinator").id
    db.flush()

    async with make_client(outgoing) as client:
        response = await client.get(_url(event, "closure"))

    assert response.status_code == 403


@pytest.mark.story("SCRUM-86")
async def test_the_coordinator_lists_their_completed_events(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator = _ended(db, make_user)
    async with make_client(coordinator) as client:
        await client.post(_url(event, "complete"), json={})
        mine = await client.get("/api/event-requests/assigned-completed")
    async with make_client(make_user("coordinator")) as client:
        theirs = await client.get("/api/event-requests/assigned-completed")

    assert [row["id"] for row in mine.json()] == [str(event.id)]
    assert theirs.json() == []


def _safety_officers(db: Session, event: EventRequest) -> set[uuid.UUID]:
    return {row.decided_by_id for row in safety_repo.list_for_event(db, event.id)}
