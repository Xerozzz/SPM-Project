"""SCRUM-29: the creating organiser can find, reopen, and keep editing a draft."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from models.user import User

MakeUser = Callable[..., User]
MakeClient = Callable[[User | None], httpx.AsyncClient]


async def create_draft(client: httpx.AsyncClient) -> dict[str, object]:
    start = datetime.now(UTC) + timedelta(days=20)
    response = await client.post(
        "/api/event-requests",
        json={
            "name": "Workshop draft",
            "purpose": "Hands-on learning",
            "start_at": start.isoformat(),
            "venue_requirement": "Seminar room-type venue",
        },
    )
    assert response.status_code == 201
    return response.json()


async def create_complete_draft(client: httpx.AsyncClient) -> dict[str, object]:
    start = datetime.now(UTC) + timedelta(days=30)
    response = await client.post(
        "/api/event-requests",
        json={
            "name": "Submitted workshop",
            "purpose": "Hands-on learning",
            "description": "A complete request for submission.",
            "start_at": start.isoformat(),
            "end_at": (start + timedelta(hours=2)).isoformat(),
            "expected_attendance": 40,
            "venue_requirement": "Seminar room-type venue",
            "accessibility_requirement": "Step-free access",
            "equipment_requirement": "Projector-type requirement",
            "layout_requirement": "Classroom",
            "registration_requirement": "Open registration",
        },
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.story("SCRUM-29")
async def test_creator_can_retrieve_their_saved_draft(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")

    async with make_client(organiser) as client:
        draft = await create_draft(client)
        response = await client.get(f"/api/event-requests/{draft['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == draft["id"]
    assert body["status"] == "draft"
    assert body["name"] == "Workshop draft"
    assert body["purpose"] == "Hands-on learning"
    assert body["venue_requirement"] == "Seminar room-type venue"
    assert body["description"] is None
    assert body["submitted_at"] is None


@pytest.mark.story("SCRUM-29")
async def test_creator_can_continue_editing_with_existing_draft_edit_flow(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")

    async with make_client(organiser) as client:
        draft = await create_draft(client)
        edit = await client.patch(
            f"/api/event-requests/{draft['id']}",
            json={"description": "Updated after reopening"},
        )
        reopened = await client.get(f"/api/event-requests/{draft['id']}")

    assert edit.status_code == 200
    assert edit.json()["status"] == "draft"
    assert edit.json()["description"] == "Updated after reopening"
    assert reopened.status_code == 200
    assert reopened.json()["description"] == "Updated after reopening"


@pytest.mark.story("SCRUM-29")
async def test_same_organisation_organiser_can_view_the_creators_draft(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    creator = make_user("organiser")
    colleague = make_user("organiser", organisation_id=creator.organisation_id)

    async with make_client(creator) as creator_client:
        draft = await create_draft(creator_client)

    async with make_client(colleague) as colleague_client:
        response = await colleague_client.get(f"/api/event-requests/{draft['id']}")
        calendar = await colleague_client.get("/api/event-requests/calendar")

    assert response.status_code == 200
    assert response.json()["id"] == draft["id"]
    assert response.json()["status"] == "draft"
    assert calendar.status_code == 200
    assert [row["id"] for row in calendar.json()] == [draft["id"]]


@pytest.mark.story("SCRUM-29")
async def test_same_organisation_organiser_cannot_edit_the_creators_draft(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    creator = make_user("organiser")
    colleague = make_user("organiser", organisation_id=creator.organisation_id)

    async with make_client(creator) as creator_client:
        draft = await create_draft(creator_client)

    async with make_client(colleague) as colleague_client:
        response = await colleague_client.patch(
            f"/api/event-requests/{draft['id']}",
            json={"description": "Changed by a colleague"},
        )

    assert response.status_code == 403


@pytest.mark.story("SCRUM-29")
async def test_outside_organisation_organiser_cannot_view_the_creators_draft(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    creator = make_user("organiser")
    outsider = make_user("organiser")

    async with make_client(creator) as creator_client:
        draft = await create_draft(creator_client)

    async with make_client(outsider) as outsider_client:
        response = await outsider_client.get(f"/api/event-requests/{draft['id']}")

    assert response.status_code == 403


@pytest.mark.story("SCRUM-29")
async def test_outside_organisation_organiser_has_no_calendar_draft_rows(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    creator = make_user("organiser")
    outsider = make_user("organiser")

    async with make_client(creator) as creator_client:
        await create_draft(creator_client)

    async with make_client(outsider) as outsider_client:
        calendar = await outsider_client.get("/api/event-requests/calendar")

    assert calendar.status_code == 200
    assert calendar.json() == []


@pytest.mark.story("SCRUM-29")
async def test_outside_organisation_organiser_cannot_edit_the_creators_draft(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    creator = make_user("organiser")
    outsider = make_user("organiser")

    async with make_client(creator) as creator_client:
        draft = await create_draft(creator_client)

    async with make_client(outsider) as outsider_client:
        response = await outsider_client.patch(
            f"/api/event-requests/{draft['id']}",
            json={"description": "Changed by someone else"},
        )

    assert response.status_code == 403


@pytest.mark.story("SCRUM-29")
async def test_coordinator_cannot_access_the_draft_calendar(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    creator = make_user("organiser")
    coordinator = make_user("coordinator", organisation_id=creator.organisation_id)

    async with make_client(creator) as creator_client:
        await create_draft(creator_client)

    async with make_client(coordinator) as coordinator_client:
        response = await coordinator_client.get("/api/event-requests/calendar")

    assert response.status_code == 403


@pytest.mark.story("SCRUM-29")
async def test_coordinator_cannot_view_a_draft(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    creator = make_user("organiser")
    coordinator = make_user("coordinator", organisation_id=creator.organisation_id)

    async with make_client(creator) as creator_client:
        draft = await create_draft(creator_client)

    async with make_client(coordinator) as coordinator_client:
        response = await coordinator_client.get(f"/api/event-requests/{draft['id']}")

    assert response.status_code == 403


@pytest.mark.story("SCRUM-29")
async def test_submitted_requests_remain_visible_to_their_creator(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    creator = make_user("organiser")

    async with make_client(creator) as client:
        draft = await create_complete_draft(client)
        submitted = await client.post(f"/api/event-requests/{draft['id']}/submit")
        reopened = await client.get(f"/api/event-requests/{draft['id']}")
        mine = await client.get("/api/event-requests")

    assert submitted.status_code == 200
    assert submitted.json()["status"] == "submitted"
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "submitted"
    assert [row["id"] for row in mine.json()] == [draft["id"]]
