"""SCRUM-29: an organiser can save an incomplete event request as a draft."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from models.event_request import EventRequest
from models.user import User

MakeUser = Callable[..., User]
MakeClient = Callable[[User | None], httpx.AsyncClient]


@pytest.mark.story("SCRUM-29")
async def test_organiser_can_create_an_incomplete_draft(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")

    async with make_client(organiser) as client:
        response = await client.post("/api/event-requests/drafts", json={"name": "Hackathon draft"})

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert body["name"] == "Hackathon draft"
    assert body["description"] is None
    assert body["expected_attendance"] is None

    saved = db.get(EventRequest, uuid.UUID(body["id"]))
    assert saved is not None
    assert saved.organiser_id == organiser.id
    assert saved.status is EventStatus.DRAFT
    assert saved.name == "Hackathon draft"
    assert saved.description is None


@pytest.mark.story("SCRUM-29")
async def test_missing_submission_fields_do_not_block_draft_save(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")

    async with make_client(organiser) as client:
        response = await client.post("/api/event-requests/drafts", json={})

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert body["name"] is None
    assert body["start_at"] is None
    assert body["end_at"] is None


@pytest.mark.story("SCRUM-29")
async def test_draft_creation_retains_supplied_values(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    start = datetime.now(UTC) + timedelta(days=30)
    payload = {
        "name": "Careers Fair",
        "purpose": "Connect students with employers",
        "start_at": start.isoformat(),
        "end_at": (start + timedelta(hours=3)).isoformat(),
        "expected_attendance": 120,
        "venue_requirement": "Hall with booths",
    }

    async with make_client(organiser) as client:
        response = await client.post("/api/event-requests/drafts", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert body["name"] == payload["name"]
    assert body["purpose"] == payload["purpose"]
    assert body["expected_attendance"] == payload["expected_attendance"]
    assert body["venue_requirement"] == payload["venue_requirement"]
    assert body["description"] is None
    assert body["submitted_at"] is None


@pytest.mark.story("SCRUM-29")
async def test_coordinator_cannot_create_a_draft(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    coordinator = make_user("coordinator")

    async with make_client(coordinator) as client:
        response = await client.post("/api/event-requests/drafts", json={"name": "Coordinator draft"})

    assert response.status_code == 403


@pytest.mark.story("SCRUM-29")
async def test_anonymous_user_cannot_create_a_draft(make_client: MakeClient) -> None:
    async with make_client(None) as client:
        response = await client.post("/api/event-requests/drafts", json={"name": "Anonymous draft"})

    assert response.status_code == 401
