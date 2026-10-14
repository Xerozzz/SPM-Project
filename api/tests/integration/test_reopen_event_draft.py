"""SCRUM-29: the creating organiser can find, reopen, and keep editing a draft."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import cast

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.dependencies import EventAccess, require_event_access
from models.equipment import Equipment
from models.user import User

MakeUser = Callable[..., User]
MakeClient = Callable[[User | None], httpx.AsyncClient]


def json_dict(response: httpx.Response) -> dict[str, object]:
    body: object = response.json()
    assert isinstance(body, dict)
    assert all(isinstance(key, str) for key in body)
    return cast(dict[str, object], body)


def claims_for(user: User) -> dict[str, object]:
    return {"sub": str(user.id), "roles": list(user.roles)}


async def create_draft(client: httpx.AsyncClient) -> dict[str, object]:
    start = datetime.now(UTC) + timedelta(days=20)
    response = await client.post(
        "/api/event-requests/drafts",
        json={
            "name": "Workshop draft",
            "purpose": "Hands-on learning",
            "start_at": start.isoformat(),
            "venue_requirement": "Seminar room-type venue",
        },
    )
    assert response.status_code == 201
    return json_dict(response)


async def create_complete_draft(db: Session, client: httpx.AsyncClient) -> dict[str, object]:
    start = datetime.now(UTC) + timedelta(days=30)
    if (
        db.query(Equipment)
        .filter(
            Equipment.equipment_type == "Projector-type requirement",
            Equipment.location == "Test Store",
        )
        .first()
        is None
    ):
        db.add(
            Equipment(
                equipment_type="Projector-type requirement",
                description=None,
                total_quantity=1,
                location="Test Store",
                operational_status="Operational",
            )
        )
        db.flush()
    response = await client.post(
        "/api/event-requests/drafts",
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
    return json_dict(response)


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
async def test_shared_event_access_allows_same_org_view_but_not_edit(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    creator = make_user("organiser")
    colleague = make_user("organiser", organisation_id=creator.organisation_id)

    async with make_client(creator) as creator_client:
        draft = await create_draft(creator_client)

    request_id = uuid.UUID(str(draft["id"]))
    viewed = require_event_access(EventAccess.VIEW)(request_id, claims_for(colleague), db)

    assert viewed.id == request_id
    with pytest.raises(HTTPException) as exc:
        require_event_access(EventAccess.EDIT)(request_id, claims_for(colleague), db)
    assert exc.value.status_code == 403


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
        drafts = await colleague_client.get("/api/event-requests/drafts")

    assert response.status_code == 200
    assert response.json()["id"] == draft["id"]
    assert response.json()["status"] == "draft"
    assert drafts.status_code == 200
    assert [row["id"] for row in drafts.json()] == [draft["id"]]


@pytest.mark.story("SCRUM-29")
async def test_same_organisation_organiser_can_view_after_submission(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    creator = make_user("organiser")
    colleague = make_user("organiser", organisation_id=creator.organisation_id)
    make_user("coordinator")

    async with make_client(creator) as creator_client:
        draft = await create_complete_draft(db, creator_client)
        submitted = await creator_client.post(f"/api/event-requests/{draft['id']}/submit")

    async with make_client(colleague) as colleague_client:
        response = await colleague_client.get(f"/api/event-requests/{draft['id']}")

    assert submitted.status_code == 200
    assert response.status_code == 200
    assert response.json()["id"] == draft["id"]
    assert response.json()["status"] == "submitted"


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
async def test_outside_organisation_organiser_has_no_visible_draft_rows(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    creator = make_user("organiser")
    outsider = make_user("organiser")

    async with make_client(creator) as creator_client:
        await create_draft(creator_client)

    async with make_client(outsider) as outsider_client:
        drafts = await outsider_client.get("/api/event-requests/drafts")

    assert drafts.status_code == 200
    assert drafts.json() == []


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
async def test_coordinator_cannot_access_visible_drafts(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    creator = make_user("organiser")
    coordinator = make_user("coordinator", organisation_id=creator.organisation_id)

    async with make_client(creator) as creator_client:
        await create_draft(creator_client)

    async with make_client(coordinator) as coordinator_client:
        response = await coordinator_client.get("/api/event-requests/drafts")

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
async def test_coordinator_can_view_a_submitted_request(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    creator = make_user("organiser")
    coordinator = make_user("coordinator")

    async with make_client(creator) as creator_client:
        draft = await create_complete_draft(db, creator_client)
        submitted = await creator_client.post(f"/api/event-requests/{draft['id']}/submit")

    async with make_client(coordinator) as coordinator_client:
        response = await coordinator_client.get(f"/api/event-requests/{draft['id']}")

    assert submitted.status_code == 200
    assert response.status_code == 200
    assert response.json()["id"] == draft["id"]
    assert response.json()["status"] == "submitted"


@pytest.mark.story("SCRUM-29")
async def test_submitted_requests_remain_visible_to_their_creator(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    creator = make_user("organiser")
    make_user("coordinator")

    async with make_client(creator) as client:
        draft = await create_complete_draft(db, client)
        submitted = await client.post(f"/api/event-requests/{draft['id']}/submit")
        reopened = await client.get(f"/api/event-requests/{draft['id']}")
        mine = await client.get("/api/event-requests")

    assert submitted.status_code == 200
    assert submitted.json()["status"] == "submitted"
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "submitted"
    assert [row["id"] for row in mine.json()] == [draft["id"]]
