"""SCRUM-30: coordinators and organisers exchange clarification messages during review."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from models.event_request import EventRequest
from models.user import User
from tests.integration.test_submit_event_request import make_draft

MakeUser = Callable[..., User]
MakeClient = Callable[[User | None], httpx.AsyncClient]


async def submitted_request(db: Session, organiser: User, make_client: MakeClient) -> EventRequest:
    request = make_draft(db, organiser)
    async with make_client(organiser) as client:
        response = await client.post(f"/api/event-requests/{request.id}/submit")
    assert response.status_code == 200
    db.refresh(request)
    return request


async def request_clarification(
    client: httpx.AsyncClient, request: EventRequest, message: str = "Which room layout is needed?"
) -> httpx.Response:
    return await client.post(
        f"/api/event-requests/{request.id}/clarifications", json={"message": message}
    )


@pytest.mark.story("SCRUM-30")
async def test_coordinator_can_create_clarification_with_audit_fields(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = await submitted_request(db, organiser, make_client)
    assert request.coordinator_id == coordinator.id

    async with make_client(coordinator) as client:
        response = await request_clarification(
            client, request, "  Which room layout is needed?  \n"
        )

    assert response.status_code == 201
    body = response.json()
    assert body["event_request_id"] == str(request.id)
    assert body["author_id"] == str(coordinator.id)
    assert body["message"] == "Which room layout is needed?"
    created_at = datetime.fromisoformat(body["created_at"].replace("Z", "+00:00"))
    assert created_at.tzinfo is not None
    assert abs(datetime.now(UTC) - created_at) < timedelta(seconds=30)


@pytest.mark.story("SCRUM-30")
async def test_coordinator_review_list_contains_submitted_requests_not_drafts(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    submitted = await submitted_request(db, organiser, make_client)
    make_draft(db, organiser, name="Still a draft")

    async with make_client(coordinator) as client:
        response = await client.get("/api/event-requests/reviewable")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [str(submitted.id)]


@pytest.mark.story("SCRUM-30")
async def test_unassigned_coordinator_can_view_but_cannot_request_clarification(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    now = datetime.now(UTC)
    assigned = make_user("coordinator", created_at=now - timedelta(minutes=1))
    unassigned = make_user("coordinator", created_at=now)
    request = await submitted_request(db, organiser, make_client)
    assert request.coordinator_id == assigned.id

    async with make_client(unassigned) as client:
        view = await client.get(f"/api/event-requests/{request.id}")
        clarification = await request_clarification(client, request)

    assert view.status_code == 200
    assert view.json()["id"] == str(request.id)
    assert clarification.status_code == 403


@pytest.mark.story("SCRUM-30")
@pytest.mark.parametrize("message", ["", "   \n\t"])
async def test_blank_coordinator_clarification_is_rejected(
    message: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = await submitted_request(db, organiser, make_client)

    async with make_client(coordinator) as client:
        response = await request_clarification(client, request, message)

    assert response.status_code == 422


@pytest.mark.story("SCRUM-30")
async def test_organiser_can_view_clarification_and_respond(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = await submitted_request(db, organiser, make_client)

    async with make_client(coordinator) as client:
        clarification = await request_clarification(client, request)

    async with make_client(organiser) as client:
        history = await client.get(f"/api/event-requests/{request.id}/clarifications")
        response = await client.post(
            f"/api/event-requests/{request.id}/clarifications/responses",
            json={"message": "Please use classroom layout."},
        )

    assert clarification.status_code == 201
    assert history.status_code == 200
    assert [entry["message"] for entry in history.json()] == ["Which room layout is needed?"]
    assert response.status_code == 201
    assert response.json()["author_id"] == str(organiser.id)
    assert response.json()["message"] == "Please use classroom layout."


@pytest.mark.story("SCRUM-30")
@pytest.mark.parametrize("message", ["", "   \n\t"])
async def test_blank_organiser_response_is_rejected(
    message: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    make_user("coordinator")
    request = await submitted_request(db, organiser, make_client)

    async with make_client(organiser) as client:
        response = await client.post(
            f"/api/event-requests/{request.id}/clarifications/responses",
            json={"message": message},
        )

    assert response.status_code == 422


@pytest.mark.story("SCRUM-30")
async def test_unrelated_organiser_cannot_view_or_contribute_to_clarification_history(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    unrelated = make_user("organiser")
    make_user("coordinator")
    request = await submitted_request(db, organiser, make_client)

    async with make_client(unrelated) as client:
        history = await client.get(f"/api/event-requests/{request.id}/clarifications")
        response = await client.post(
            f"/api/event-requests/{request.id}/clarifications/responses",
            json={"message": "An unrelated response"},
        )

    assert history.status_code == 403
    assert response.status_code == 403


@pytest.mark.story("SCRUM-30")
async def test_coordinator_cannot_request_clarification_on_a_draft(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = make_draft(db, organiser)

    async with make_client(coordinator) as client:
        response = await request_clarification(client, request)
        history = await client.get(f"/api/event-requests/{request.id}/clarifications")

    assert response.status_code == 403
    assert history.status_code == 403


@pytest.mark.story("SCRUM-30")
async def test_participant_roles_cannot_use_each_others_message_endpoint(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = await submitted_request(db, organiser, make_client)

    async with make_client(organiser) as client:
        organiser_request = await request_clarification(client, request)
    async with make_client(coordinator) as client:
        coordinator_response = await client.post(
            f"/api/event-requests/{request.id}/clarifications/responses",
            json={"message": "This is not an organiser response"},
        )

    assert organiser_request.status_code == 403
    assert coordinator_response.status_code == 403


@pytest.mark.story("SCRUM-30")
async def test_organiser_still_cannot_edit_submitted_request(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    make_user("coordinator")
    request = await submitted_request(db, organiser, make_client)

    async with make_client(organiser) as client:
        response = await client.patch(
            f"/api/event-requests/{request.id}", json={"name": "Changed after submission"}
        )

    assert response.status_code == 409
    db.refresh(request)
    assert request.name == "Orientation Day"
    assert request.status is EventStatus.SUBMITTED


@pytest.mark.story("SCRUM-30")
async def test_clarification_and_response_leave_status_unchanged(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = await submitted_request(db, organiser, make_client)

    async with make_client(coordinator) as client:
        clarification = await request_clarification(client, request)
    db.refresh(request)
    assert clarification.status_code == 201
    assert request.status is EventStatus.SUBMITTED

    async with make_client(organiser) as client:
        response = await client.post(
            f"/api/event-requests/{request.id}/clarifications/responses",
            json={"message": "The layout should be classroom style."},
        )
    db.refresh(request)
    assert response.status_code == 201
    assert request.status is EventStatus.SUBMITTED


@pytest.mark.story("SCRUM-30")
async def test_history_persists_in_deterministic_order(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = await submitted_request(db, organiser, make_client)

    async with make_client(coordinator) as client:
        first = await request_clarification(client, request, "First question")
    async with make_client(organiser) as client:
        second = await client.post(
            f"/api/event-requests/{request.id}/clarifications/responses",
            json={"message": "First response"},
        )
    async with make_client(coordinator) as client:
        third = await request_clarification(client, request, "Follow-up question")
        history = await client.get(f"/api/event-requests/{request.id}/clarifications")

    assert [first.status_code, second.status_code, third.status_code] == [201, 201, 201]
    assert history.status_code == 200
    assert [entry["message"] for entry in history.json()] == [
        "First question",
        "First response",
        "Follow-up question",
    ]
