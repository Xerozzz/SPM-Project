"""SCRUM-35: the API tells the client what a request's status permits, so no caller has to
re-derive the rules from the status itself.
"""

from collections.abc import Callable

import httpx
import pytest
from sqlalchemy.orm import Session

from models.user import User
from tests.integration.test_submit_event_request import make_draft

MakeUser = Callable[..., User]
MakeClient = Callable[[User | None], httpx.AsyncClient]


@pytest.mark.story("SCRUM-35")
async def test_a_draft_is_listed_with_edit_and_submit(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    make_draft(db, organiser)

    async with make_client(organiser) as client:
        response = await client.get("/api/event-requests")

    assert response.status_code == 200
    assert response.json()[0]["status_permits"] == ["edit", "submit"]


@pytest.mark.story("SCRUM-35")
async def test_a_submitted_request_is_listed_with_coordinator_decisions(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    # Unreferenced, but submit assigns a coordinator round-robin and needs one to exist.
    make_user("coordinator")
    draft = make_draft(db, organiser)

    async with make_client(organiser) as client:
        submit_response = await client.post(f"/api/event-requests/{draft.id}/submit")
        response = await client.get("/api/event-requests")

    assert submit_response.status_code == 200
    assert response.status_code == 200
    assert response.json()[0]["status_permits"] == ["approve", "cancel", "reject"]


@pytest.mark.story("SCRUM-35")
async def test_submitting_a_draft_returns_its_new_actions(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    # Unreferenced, but submit assigns a coordinator round-robin and needs one to exist.
    make_user("coordinator")
    draft = make_draft(db, organiser)

    async with make_client(organiser) as client:
        response = await client.post(f"/api/event-requests/{draft.id}/submit")

    assert response.status_code == 200
    assert response.json()["status_permits"] == ["approve", "cancel", "reject"]
