"""SCRUM-37: the owning Organiser proposes significant changes; nothing is applied."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from domain.event_change import Proposal
from domain.event_status import EventStatus
from domain.venue_booking import BookingStatus
from models.event_change_request import EventChangeItem, EventChangeRequest
from models.event_request import EventRequest
from models.user import User
from models.venue_booking import VenueBooking
from repositories import event_change_requests as change_repo
from services import event_change_requests as service
from services.event_requests import EventRequestNotFoundError, NotAuthorisedError
from tests.integration.test_equipment_requirements import catalogue, stored
from tests.integration.test_submit_event_request import (
    MakeClient,
    MakeUser,
    content_of,
    make_draft,
)
from tests.integration.test_submit_venue_booking import approved_event, seed_equipment
from tests.integration.test_venue_search import effective_for, make_venue

_H = timedelta(hours=1)


def _planned(
    db: Session, make_user: MakeUser, status: EventStatus = EventStatus.APPROVED
) -> tuple[EventRequest, User, User, VenueBooking]:
    """An event with a coordinator, one session and one equipment line."""
    organiser, coordinator = make_user("organiser"), make_user("coordinator")
    event = approved_event(db, organiser, coordinator)
    event.status = status
    seed_equipment(db, event)
    catalogue(db, "Microphone")
    venue = make_venue(db)
    assert event.start_at is not None and event.end_at is not None
    start, end = event.start_at, event.start_at + 2 * _H
    effective_start, effective_end = effective_for(venue, start, end)
    session = VenueBooking(
        venue_id=venue.id,
        event_request_id=event.id,
        requested_by_id=coordinator.id,
        session_label="Keynote",
        start_at=start,
        end_at=end,
        effective_start_at=effective_start,
        effective_end_at=effective_end,
        status=BookingStatus.PENDING,
    )
    db.add(session)
    db.flush()
    return event, organiser, coordinator, session


def _body(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "submission_key": str(uuid.uuid4()),
        "reason": "More people signed up",
        "event": {"expected_attendance": 180},
    }
    values.update(overrides)
    return values


async def _propose(
    client: httpx.AsyncClient, event: EventRequest, body: dict[str, Any]
) -> httpx.Response:
    return await client.post(f"/api/event-requests/{event.id}/change-requests", json=body)


def _count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(EventChangeRequest)) or 0


def _items(response: httpx.Response) -> list[tuple[str, str, Any, Any]]:
    return [
        (i["target"], i["field"], i["current_value"], i["proposed_value"])
        for i in response.json()["items"]
    ]


# --------------------------------------------------------------------------- AC1, AC2, AC3


@pytest.mark.story("SCRUM-37")
@pytest.mark.parametrize(
    "status", [EventStatus.SUBMITTED, EventStatus.APPROVED, EventStatus.CONFIRMED]
)
async def test_the_owning_organiser_proposes_a_change(
    status: EventStatus, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, _, _ = _planned(db, make_user, status)

    async with make_client(organiser) as client:
        response = await _propose(client, event, _body())

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["reason"] == "More people signed up"
    assert body["requested_by_id"] == str(organiser.id)
    assert _items(response) == [("event", "expected_attendance", 200, 180)]


@pytest.mark.story("SCRUM-37")
async def test_one_request_carries_event_session_and_equipment_changes(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, _, session = _planned(db, make_user)
    [projector] = stored(db, event)
    assert event.start_at is not None and event.end_at is not None
    later = event.start_at + 24 * _H
    body = _body(
        reason="Moved to the next day",
        event={"start_at": later.isoformat(), "end_at": (later + 4 * _H).isoformat()},
        sessions=[
            {
                "booking_id": str(session.id),
                "start_at": later.isoformat(),
                "end_at": (later + 2 * _H).isoformat(),
            }
        ],
        equipment=[
            {"requirement_id": str(projector.id), "quantity": 3},
            {"equipment_type": "Microphone", "quantity": 2},
        ],
    )

    async with make_client(organiser) as client:
        response = await _propose(client, event, body)

    assert response.status_code == 201
    fields = [(target, name) for target, name, _, _ in _items(response)]
    assert fields == [
        ("event", "start_at"),
        ("event", "end_at"),
        ("session", "start_at"),
        ("session", "end_at"),
        ("equipment", "quantity"),
        ("equipment", "add"),
    ]
    # AC3: the snapshot keeps the event version the proposal was made against.
    assert response.json()["event_updated_at"] is not None


@pytest.mark.story("SCRUM-37")
async def test_a_layout_change_uses_this_flow(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, _, _ = _planned(db, make_user)

    async with make_client(organiser) as client:
        response = await _propose(client, event, _body(event={"layout_requirement": "Banquet"}))

    assert response.status_code == 201
    assert _items(response) == [("event", "layout_requirement", "Theatre style", "Banquet")]


# --------------------------------------------------------------------------- AC5


@pytest.mark.story("SCRUM-37")
async def test_proposing_changes_nothing_on_the_event_or_its_arrangements(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, _, session = _planned(db, make_user, EventStatus.CONFIRMED)
    [projector] = stored(db, event)
    before = (content_of(event), session.start_at, projector.quantity)

    async with make_client(organiser) as client:
        response = await _propose(
            client,
            event,
            _body(
                event={"expected_attendance": 300},
                equipment=[{"requirement_id": str(projector.id), "quantity": 5}],
            ),
        )

    assert response.status_code == 201
    db.refresh(event)
    db.refresh(session)
    db.refresh(projector)
    assert (content_of(event), session.start_at, projector.quantity) == before
    # A Confirmed event does not revert just because a change was proposed.
    assert event.status is EventStatus.CONFIRMED


# --------------------------------------------------------------------------- AC4


@pytest.mark.story("SCRUM-37")
async def test_an_invalid_value_creates_no_request(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, _, session = _planned(db, make_user)
    assert event.end_at is not None
    body = _body(
        event={"expected_attendance": 0, "venue_requirement": "Nowhere"},
        sessions=[{"booking_id": str(session.id), "end_at": (event.end_at + _H).isoformat()}],
        equipment=[{"equipment_type": "Smoke machine", "quantity": 1}],
    )

    async with make_client(organiser) as client:
        response = await _propose(client, event, body)

    assert response.status_code == 422
    assert {p["field"] for p in response.json()["detail"]} == {
        "event.expected_attendance",
        "event.venue_requirement",
        "sessions[0].end_at",
        "equipment[0].equipment_type",
    }
    assert _count(db) == 0


@pytest.mark.story("SCRUM-37")
@pytest.mark.parametrize(
    "body",
    [
        _body(reason="  "),
        _body(event={}),
        _body(event={"name": "Renamed"}),
        _body(event={"start_at": "2030-01-01T09:00:00"}),
    ],
)
async def test_a_blank_reason_empty_proposal_or_ordinary_field_is_refused(
    body: dict[str, Any], db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, _, _ = _planned(db, make_user)

    async with make_client(organiser) as client:
        response = await _propose(client, event, body)

    assert response.status_code == 422
    assert _count(db) == 0


# --------------------------------------------------------------------------- AC6


@pytest.mark.story("SCRUM-37")
async def test_the_assigned_coordinator_reads_pending_requests(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, coordinator, _ = _planned(db, make_user)
    async with make_client(organiser) as client:
        created = await _propose(client, event, _body())

    async with make_client(coordinator) as client:
        listed = await client.get(f"/api/event-requests/{event.id}/change-requests")

    assert listed.status_code == 200
    [row] = listed.json()
    assert row["id"] == created.json()["id"]
    assert row["items"][0]["proposed_value"] == 180


@pytest.mark.story("SCRUM-37")
async def test_reassignment_moves_read_access_to_the_new_coordinator(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, old, _ = _planned(db, make_user)
    async with make_client(organiser) as client:
        await _propose(client, event, _body())
    new = make_user("coordinator")
    event.coordinator_id = new.id
    db.flush()

    async with make_client(old) as client:
        refused = await client.get(f"/api/event-requests/{event.id}/change-requests")
    async with make_client(new) as client:
        allowed = await client.get(f"/api/event-requests/{event.id}/change-requests")

    assert refused.status_code == 403
    assert allowed.status_code == 200 and len(allowed.json()) == 1


@pytest.mark.story("SCRUM-37")
@pytest.mark.parametrize("who", ["other_organiser", "other_coordinator", "venue_staff", "lead"])
async def test_others_cannot_read_change_requests(
    who: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, _, _ = _planned(db, make_user)
    roles = {
        "other_organiser": "organiser",
        "other_coordinator": "coordinator",
        "venue_staff": "venue_staff",
        "lead": "coordinator_lead",
    }

    async with make_client(make_user(roles[who])) as client:
        response = await client.get(f"/api/event-requests/{event.id}/change-requests")

    assert response.status_code == 403


@pytest.mark.story("SCRUM-37")
@pytest.mark.parametrize("role", ["organiser", "coordinator", "coordinator_lead", "venue_staff"])
async def test_only_the_owning_organiser_may_propose(
    role: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator, _ = _planned(db, make_user)
    caller: User = coordinator if role == "coordinator" else make_user(role)

    async with make_client(caller) as client:
        response = await _propose(client, event, _body())

    assert response.status_code == 403
    assert _count(db) == 0


@pytest.mark.story("SCRUM-37")
async def test_a_signed_out_user_is_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, _, _ = _planned(db, make_user)

    async with make_client(None) as client:
        response = await _propose(client, event, _body())

    assert response.status_code == 401


# --------------------------------------------------------------------------- AC7


@pytest.mark.story("SCRUM-37")
@pytest.mark.parametrize("status", [EventStatus.DRAFT, EventStatus.REJECTED])
async def test_drafts_and_rejected_events_cannot_use_this_flow(
    status: EventStatus, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    event = make_draft(db, organiser)
    event.status = status
    db.flush()

    async with make_client(organiser) as client:
        response = await _propose(client, event, _body())

    assert response.status_code == 403
    assert _count(db) == 0


@pytest.mark.story("SCRUM-37")
async def test_the_shared_dependency_refuses_a_draft_before_the_body_is_read(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC7 comes from require_event_access(PROPOSE_CHANGE), not only from the service.
    The dependency runs before the body is validated, so a body that would be a 422 is a
    403 on a Draft."""
    organiser = make_user("organiser")
    event = make_draft(db, organiser)

    async with make_client(organiser) as client:
        response = await _propose(client, event, _body(event={"name": "New name"}))

    assert response.status_code == 403


# --------------------------------------------------------------------------- AC8


@pytest.mark.story("SCRUM-37")
async def test_a_retried_submit_returns_the_first_request(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, _, _ = _planned(db, make_user)
    body = _body()

    async with make_client(organiser) as client:
        first = await _propose(client, event, body)
        retry = await _propose(client, event, body)
        another = await _propose(client, event, _body())

    assert (first.status_code, retry.status_code, another.status_code) == (201, 200, 201)
    assert retry.json()["id"] == first.json()["id"]
    assert _count(db) == 2


@pytest.mark.story("SCRUM-37")
def test_a_submit_that_loses_the_race_returns_the_winner(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two copies of one submit both pass the first lookup; the unique key decides."""
    event, organiser, _, _ = _planned(db, make_user)
    key = uuid.uuid4()
    proposal = _proposal()
    winner, created = service.submit(db, event.id, organiser.id, proposal, key, _now())
    assert created
    real = change_repo.get_by_submission
    lookups: list[uuid.UUID] = []

    def first_lookup_misses(
        session: Session, event_id: uuid.UUID, submission_key: uuid.UUID
    ) -> EventChangeRequest | None:
        lookups.append(submission_key)
        return None if len(lookups) == 1 else real(session, event_id, submission_key)

    monkeypatch.setattr(change_repo, "get_by_submission", first_lookup_misses)

    again, created_again = service.submit(db, event.id, organiser.id, proposal, key, _now())

    assert not created_again
    assert again.id == winner.id
    assert _count(db) == 1


@pytest.mark.story("SCRUM-37")
def test_the_service_rechecks_the_owner_and_status_on_the_locked_row(
    db: Session, make_user: MakeUser
) -> None:
    event, organiser, _, _ = _planned(db, make_user)
    event.status = EventStatus.REJECTED
    db.flush()

    with pytest.raises(NotAuthorisedError):
        service.submit(db, event.id, organiser.id, _proposal(), uuid.uuid4(), _now())
    with pytest.raises(EventRequestNotFoundError):
        service.submit(db, uuid.uuid4(), organiser.id, _proposal(), uuid.uuid4(), _now())
    assert db.scalar(select(func.count()).select_from(EventChangeItem)) == 0


def _proposal() -> Proposal:
    return Proposal(reason="r", event={"expected_attendance": 150})


def _now() -> datetime:
    return datetime.now(UTC)
