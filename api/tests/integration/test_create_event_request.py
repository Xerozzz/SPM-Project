"""SCRUM-28: organisers create a complete event request as an unsubmitted draft."""

from typing import Callable

import httpx
import pytest
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from models.event_request import EventRequest
from models.user import User

MakeUser = Callable[..., User]
MakeClient = Callable[[User | None], httpx.AsyncClient]


def request_body(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "name": "Orientation Day",
        "purpose": "Welcome new students",
        "description": "Talks, campus tours and student-group introductions.",
        "start_at": "2026-12-01T09:00:00+08:00",
        "end_at": "2026-12-01T13:00:00+08:00",
        "expected_attendance": 200,
        "venue_requirement": "Auditorium for 200 people",
        "accessibility_requirement": "Step-free access and a hearing loop",
        "equipment_requirement": "Projector and two microphones",
        "layout_requirement": "Theatre style",
        "registration_requirement": "Open registration, capped at 200",
    }
    values.update(overrides)
    return values


@pytest.mark.story("SCRUM-28")
async def test_an_organiser_creates_a_complete_unsubmitted_draft(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")

    async with make_client(organiser) as client:
        response = await client.post("/api/event-requests", json=request_body())

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert body["submitted_at"] is None
    assert body["venue_requirement"] == "Auditorium for 200 people"
    assert body["equipment_requirement"] == "Projector and two microphones"
    # The timezone-aware input is normalised to UTC before it reaches storage.
    assert body["start_at"] == "2026-12-01T01:00:00Z"

    saved = db.get(EventRequest, body["id"])
    assert saved is not None
    assert saved.organiser_id == organiser.id
    assert saved.status is EventStatus.DRAFT
    assert saved.submitted_at is None


@pytest.mark.story("SCRUM-28")
async def test_missing_or_invalid_fields_are_identified_without_creating_a_draft(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    invalid = request_body(name="", end_at="2026-12-01T08:00:00+08:00", expected_attendance=0)

    async with make_client(organiser) as client:
        response = await client.post("/api/event-requests", json=invalid)

    assert response.status_code == 422
    details = response.json()["detail"]
    assert any(problem["loc"][-1] == "name" for problem in details)
    assert any(problem["loc"][-1] == "expected_attendance" for problem in details)
    assert any(problem["loc"][-1] == "end_at" for problem in details)
    assert db.query(EventRequest).count() == 0


@pytest.mark.story("SCRUM-28")
async def test_only_an_authenticated_organiser_can_create_a_draft(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(None) as anonymous:
        assert (await anonymous.post("/api/event-requests", json=request_body())).status_code == 401

    async with make_client(make_user("coordinator")) as coordinator:
        response = await coordinator.post("/api/event-requests", json=request_body())
        assert response.status_code == 403


@pytest.mark.story("SCRUM-28")
async def test_naive_datetimes_are_rejected(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("organiser")) as client:
        response = await client.post(
            "/api/event-requests",
            json=request_body(start_at="2026-12-01T09:00:00"),
        )

    assert response.status_code == 422
