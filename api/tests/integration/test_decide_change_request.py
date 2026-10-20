"""SCRUM-47: the assigned Coordinator decides a significant-change request."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy.orm import Session

from domain.change_decision import Decision
from domain.event_status import EventStatus
from models.event_request import EventRequest
from models.user import User
from schemas.event_change_requests import EventChangeRequestCreate
from services import event_change_requests as service
from services.event_requests import NotAuthorisedError
from tests.integration.test_equipment_requirements import stored
from tests.integration.test_event_change_requests import _body, _planned, _propose
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_submit_venue_booking import approved_event

_H = timedelta(hours=1)


async def _proposed(
    db: Session,
    make_user: MakeUser,
    make_client: MakeClient,
    status: EventStatus = EventStatus.APPROVED,
    **body: Any,
) -> tuple[EventRequest, User, User, str]:
    """A planned event with one pending change request. Returns its id too."""
    event, organiser, coordinator, _ = _planned(db, make_user, status)
    async with make_client(organiser) as client:
        response = await _propose(client, event, _body(**body))
    assert response.status_code == 201, response.text
    return event, organiser, coordinator, response.json()["id"]


async def _decide(
    client: httpx.AsyncClient,
    event: EventRequest,
    change_id: str,
    decision: str = "approve",
    note: str = "Fits the plan",
) -> httpx.Response:
    return await client.post(
        f"/api/event-requests/{event.id}/change-requests/{change_id}/decision",
        json={"decision": decision, "note": note},
    )


# --------------------------------------------------------------------------- AC1, AC3


@pytest.mark.story("SCRUM-47")
async def test_approval_applies_the_event_fields_and_records_the_decision(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, coordinator, change_id = await _proposed(db, make_user, make_client)

    async with make_client(coordinator) as client:
        response = await _decide(client, event, change_id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "approved"
    assert body["decided_by_id"] == str(coordinator.id)
    assert body["decided_at"] is not None
    assert body["decision_note"] == "Fits the plan"
    assert [i["outcome"] for i in body["items"]] == ["applied"]
    db.refresh(event)
    assert event.expected_attendance == 180
    # The Organiser sees the decision on their own list.
    async with make_client(organiser) as client:
        listed = await client.get(f"/api/event-requests/{event.id}/change-requests")
    assert listed.json()[0]["status"] == "approved"


@pytest.mark.story("SCRUM-47")
async def test_a_blank_note_is_refused_and_nothing_changes(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator, change_id = await _proposed(db, make_user, make_client)

    async with make_client(coordinator) as client:
        response = await _decide(client, event, change_id, note="   ")

    assert response.status_code == 422
    assert response.json()["detail"] == [{"field": "note", "reason": "is required"}]
    db.refresh(event)
    assert event.expected_attendance == 200


@pytest.mark.story("SCRUM-47")
async def test_only_the_current_assigned_coordinator_decides(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, old, change_id = await _proposed(db, make_user, make_client)
    new = make_user("coordinator")
    event.coordinator_id = new.id
    db.flush()

    for user in (organiser, old, make_user("coordinator"), make_user("coordinator_lead")):
        async with make_client(user) as client:
            response = await _decide(client, event, change_id)
        assert response.status_code == 403
    async with make_client(new) as client:
        response = await _decide(client, event, change_id)
    assert response.status_code == 200


@pytest.mark.story("SCRUM-47")
async def test_the_shared_dependency_refuses_before_the_body_is_read(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1 comes from require_event_access(DECIDE_CHANGE_REQUEST): an unrelated Coordinator
    gets 403 even with a body that would be a 422."""
    event, _, _, change_id = await _proposed(db, make_user, make_client)

    async with make_client(make_user("coordinator")) as client:
        response = await client.post(
            f"/api/event-requests/{event.id}/change-requests/{change_id}/decision",
            json={"decision": "maybe"},
        )

    assert response.status_code == 403


@pytest.mark.story("SCRUM-47")
async def test_an_unknown_or_other_events_request_is_not_found(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator, _ = await _proposed(db, make_user, make_client)
    other_owner = make_user("organiser")
    other = approved_event(db, other_owner, coordinator)
    other_change, _ = service.submit(
        db,
        other.id,
        other_owner.id,
        EventChangeRequestCreate.model_validate(_body()).to_proposal(),
        uuid.uuid4(),
        datetime.now(UTC),
    )

    async with make_client(coordinator) as client:
        unknown = await _decide(client, event, str(uuid.uuid4()))
        elsewhere = await _decide(client, event, str(other_change.id))

    assert unknown.status_code == 404
    assert elsewhere.status_code == 404


# --------------------------------------------------------------------------- AC6


@pytest.mark.story("SCRUM-47")
async def test_rejection_keeps_the_event_and_records_the_reason(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator, change_id = await _proposed(
        db, make_user, make_client, EventStatus.CONFIRMED
    )

    async with make_client(coordinator) as client:
        response = await _decide(client, event, change_id, "reject", "Hall is too small")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["decision_note"] == "Hall is too small"
    assert [i["outcome"] for i in body["items"]] == [None]
    db.refresh(event)
    assert event.expected_attendance == 200
    assert event.status is EventStatus.CONFIRMED


# --------------------------------------------------------------------------- AC2


@pytest.mark.story("SCRUM-47")
async def test_a_stale_request_is_refused_and_stays_pending(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator, change_id = await _proposed(db, make_user, make_client)
    event.expected_attendance = 190
    db.flush()

    async with make_client(coordinator) as client:
        response = await _decide(client, event, change_id)
        listed = await client.get(f"/api/event-requests/{event.id}/change-requests")

    assert response.status_code == 409
    assert response.json()["detail"] == [
        {"field": "items[0]", "reason": "has changed since the request was made"}
    ]
    assert listed.json()[0]["status"] == "pending"
    db.refresh(event)
    assert event.expected_attendance == 190


@pytest.mark.story("SCRUM-47")
async def test_an_unrelated_event_update_does_not_make_a_request_stale(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator, change_id = await _proposed(db, make_user, make_client)
    event.purpose = "A new purpose"
    db.flush()

    async with make_client(coordinator) as client:
        response = await _decide(client, event, change_id)

    assert response.status_code == 200


@pytest.mark.story("SCRUM-47")
async def test_a_value_no_longer_valid_today_is_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """A proposed start that was in the future when proposed may be in the past now."""
    event, _, coordinator, _ = _planned(db, make_user)
    assert event.start_at is not None and event.end_at is not None
    sooner = {
        "start_at": (event.start_at - _H).isoformat(),
        "end_at": event.end_at.isoformat(),
    }
    created = service.submit(
        db,
        event.id,
        event.organiser_id,
        EventChangeRequestCreate.model_validate(
            _body(event={"start_at": sooner["start_at"]})
        ).to_proposal(),
        uuid.uuid4(),
        datetime.now(UTC),
    )[0]
    change_id = str(created.id)
    later = event.start_at + 30 * 24 * _H

    with pytest.raises(service.InvalidChangeRequestError):
        service.decide(
            db, event.id, uuid.UUID(change_id), coordinator.id, Decision.APPROVE, "ok", later
        )

    db.refresh(event)
    assert event.start_at.isoformat() != sooner["start_at"]


# --------------------------------------------------------------------------- AC4, AC8


@pytest.mark.story("SCRUM-47")
async def test_session_and_equipment_items_are_left_for_replanning(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, coordinator, session = _planned(db, make_user)
    [projector] = stored(db, event)
    assert event.end_at is not None
    body = _body(
        event={"expected_attendance": 190},
        sessions=[{"booking_id": str(session.id), "session_label": "Opening"}],
        equipment=[{"requirement_id": str(projector.id), "quantity": 5}],
    )
    async with make_client(organiser) as client:
        created = await _propose(client, event, body)
    before = (session.session_label, session.start_at, projector.quantity)

    async with make_client(coordinator) as client:
        response = await _decide(client, event, created.json()["id"])

    assert response.status_code == 200
    assert [(i["target"], i["outcome"]) for i in response.json()["items"]] == [
        ("event", "applied"),
        ("session", "needs_replanning"),
        ("equipment", "needs_replanning"),
    ]
    db.refresh(session)
    db.refresh(projector)
    assert (session.session_label, session.start_at, projector.quantity) == before


# --------------------------------------------------------------------------- AC5


@pytest.mark.story("SCRUM-47")
async def test_approval_returns_a_confirmed_event_to_planning(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator, change_id = await _proposed(
        db, make_user, make_client, EventStatus.CONFIRMED
    )

    async with make_client(coordinator) as client:
        response = await _decide(client, event, change_id)

    assert response.status_code == 200
    db.refresh(event)
    assert event.status is EventStatus.APPROVED


# --------------------------------------------------------------------------- AC9


@pytest.mark.story("SCRUM-47")
@pytest.mark.parametrize("second", ["approve", "reject"])
async def test_a_request_is_decided_once(
    second: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator, change_id = await _proposed(db, make_user, make_client)

    async with make_client(coordinator) as client:
        first = await _decide(client, event, change_id)
        again = await _decide(client, event, change_id, second)

    assert first.status_code == 200
    assert again.status_code == 409
    assert again.json()["detail"] == "this change request is already approved"


def test_the_service_rechecks_the_coordinator_on_the_locked_row(
    db: Session, make_user: MakeUser
) -> None:
    event, _, _, _ = _planned(db, make_user)

    with pytest.raises(NotAuthorisedError):
        service.decide(
            db,
            event.id,
            uuid.uuid4(),
            make_user("coordinator").id,
            Decision.REJECT,
            "no",
            datetime.now(UTC),
        )
