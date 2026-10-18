"""SCRUM-94: an organiser is notified when their event request is decided.

An approval or rejection stages exactly one unread notification for the owning
organiser — naming the event, the decision, and the decision time — in the same
transaction as the decision itself. The rejection reason stays on the event
(visible through the authorised event view), never copied into the notification.
"""

from typing import Any

import httpx
import pytest
from sqlalchemy.orm import Session

from models.event_request import EventRequest
from models.user import User
from tests.integration.test_submit_event_request import MakeClient, MakeUser, make_draft


async def _submit(client: httpx.AsyncClient, request_id: object) -> None:
    response = await client.post(f"/api/event-requests/{request_id}/submit")
    assert response.status_code == 200


async def _submitted_request(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> tuple[EventRequest, User, User]:
    """A submitted request assigned to its coordinator."""
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = make_draft(db, organiser)
    async with make_client(organiser) as client:
        await _submit(client, request.id)
    request.coordinator_id = coordinator.id
    db.flush()
    return request, organiser, coordinator


async def _inbox(client: httpx.AsyncClient) -> Any:
    response = await client.get("/api/notifications")
    assert response.status_code == 200
    return response.json()


@pytest.mark.story("SCRUM-94")
async def test_approval_notifies_the_owning_organiser_once(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """TC-94-01: one unread approval notification naming the event, decision, and time."""
    request, organiser, coordinator = await _submitted_request(db, make_user, make_client)

    async with make_client(coordinator) as client:
        approval = await client.post(f"/api/event-requests/{request.id}/approve")

    assert approval.status_code == 200
    decided_at = approval.json()["decided_at"]
    async with make_client(organiser) as client:
        items = await _inbox(client)

    assert len(items) == 1
    (item,) = items
    assert item["event_request_id"] == str(request.id)
    assert item["type"] == "request_approved"
    assert item["is_unread"] is True
    assert item["occurred_at"] == decided_at


@pytest.mark.story("SCRUM-94")
async def test_rejection_notifies_without_copying_the_reason(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """TC-94-02: one unread rejection notification; the reason is not in its text."""
    request, organiser, coordinator = await _submitted_request(db, make_user, make_client)

    async with make_client(coordinator) as client:
        rejected = await client.post(
            f"/api/event-requests/{request.id}/reject",
            json={"reason": "Please provide a more accessible venue."},
        )

    assert rejected.status_code == 200
    async with make_client(organiser) as client:
        items = await _inbox(client)

    assert len(items) == 1
    (item,) = items
    assert item["event_request_id"] == str(request.id)
    assert item["type"] == "request_rejected"
    assert item["is_unread"] is True
    assert item["occurred_at"] == rejected.json()["decided_at"]
    assert "rejection_reason" not in item
    assert "accessible venue" not in str(item)


@pytest.mark.story("SCRUM-94")
async def test_rejection_reason_is_read_through_the_authorised_event_view(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """TC-94-03: the organiser reads the reason from their own event, not the inbox."""
    request, organiser, coordinator = await _submitted_request(db, make_user, make_client)

    async with make_client(coordinator) as client:
        await client.post(
            f"/api/event-requests/{request.id}/reject",
            json={"reason": "Please provide a more accessible venue."},
        )
    async with make_client(organiser) as client:
        detail = await client.get(f"/api/event-requests/{request.id}")

    assert detail.status_code == 200
    assert detail.json()["rejection_reason"] == "Please provide a more accessible venue."


@pytest.mark.story("SCRUM-94")
async def test_only_the_owning_organiser_is_notified(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """TC-94-04: the deciding coordinator and anyone else see no new notification."""
    request, organiser, coordinator = await _submitted_request(db, make_user, make_client)
    lead = make_user("coordinator_lead")

    async with make_client(coordinator) as client:
        approval = await client.post(f"/api/event-requests/{request.id}/approve")
    assert approval.status_code == 200

    async with make_client(coordinator) as client:
        assert await _inbox(client) == []
    async with make_client(lead) as client:
        assert await _inbox(client) == []
    async with make_client(organiser) as client:
        assert len(await _inbox(client)) == 1


@pytest.mark.story("SCRUM-94")
async def test_unauthorised_decision_attempt_notifies_nobody(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """TC-94-05: a coordinator who is not assigned cannot decide, so nothing is staged."""
    request, organiser, coordinator = await _submitted_request(db, make_user, make_client)
    outsider = make_user("coordinator")

    async with make_client(outsider) as client:
        refused = await client.post(f"/api/event-requests/{request.id}/approve")

    assert refused.status_code == 403
    async with make_client(organiser) as client:
        assert await _inbox(client) == []


@pytest.mark.story("SCRUM-94")
async def test_decision_in_an_invalid_state_notifies_nobody(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """TC-94-06: approving a draft (never submitted) is refused and stages nothing."""
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = make_draft(db, organiser)
    request.coordinator_id = coordinator.id
    db.flush()

    async with make_client(coordinator) as client:
        refused = await client.post(f"/api/event-requests/{request.id}/approve")

    # The DECIDE dependency refuses before the service: a draft is not decidable.
    assert refused.status_code == 403
    async with make_client(organiser) as client:
        assert await _inbox(client) == []


@pytest.mark.story("SCRUM-94")
async def test_repeated_decision_does_not_duplicate_the_notification(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """TC-94-07: a second decision is refused, so the inbox stays at one."""
    request, organiser, coordinator = await _submitted_request(db, make_user, make_client)

    async with make_client(coordinator) as client:
        first = await client.post(f"/api/event-requests/{request.id}/approve")
        second = await client.post(f"/api/event-requests/{request.id}/approve")

    assert first.status_code == 200
    # The DECIDE dependency refuses before the service: an approved request is no
    # longer decidable, so no second notification can be staged.
    assert second.status_code == 403
    async with make_client(organiser) as client:
        assert len(await _inbox(client)) == 1


@pytest.mark.story("SCRUM-94")
async def test_decision_and_notification_commit_together(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """TC-94-08: after the approve response, the decision and its notification are
    both visible — neither commits without the other."""
    request, organiser, coordinator = await _submitted_request(db, make_user, make_client)

    async with make_client(coordinator) as client:
        approval = await client.post(f"/api/event-requests/{request.id}/approve")
    assert approval.status_code == 200

    async with make_client(organiser) as client:
        detail = await client.get(f"/api/event-requests/{request.id}")
        items = await _inbox(client)

    assert detail.json()["status"] == "approved"
    assert len(items) == 1
    assert items[0]["event_request_id"] == str(request.id)
