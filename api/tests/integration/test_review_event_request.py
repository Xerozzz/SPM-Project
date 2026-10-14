"""SCRUM-31: an Event Coordinator reviews and decides submitted event requests."""

import httpx
import pytest
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from tests.integration.test_submit_event_request import MakeClient, MakeUser, make_draft


async def _submit(client: httpx.AsyncClient, request_id: object) -> None:
    response = await client.post(f"/api/event-requests/{request_id}/submit")
    assert response.status_code == 200


@pytest.mark.story("SCRUM-31")
async def test_coordinator_sees_submitted_request_information_and_approves_it(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = make_draft(db, organiser)

    async with make_client(organiser) as client:
        await _submit(client, request.id)
    # SCRUM-101: submission leaves the request unassigned; the Lead's assignment
    # (SCRUM-98) is not built yet, so the test arranges ownership directly.
    request.coordinator_id = coordinator.id
    db.flush()
    async with make_client(coordinator) as client:
        review = await client.get("/api/event-requests/reviewable")
        approval = await client.post(f"/api/event-requests/{request.id}/approve")

    assert review.status_code == 200
    item = review.json()[0]
    assert item["id"] == str(request.id)
    assert item["status"] == "submitted"
    assert item["name"] == "Orientation Day"
    assert item["purpose"] == "Welcome new students"
    assert item["venue_requirement"] == "Event Submission Test Hall"
    assert item["equipment_requirement"] == "Projector"
    assert item["decided_by_id"] is None
    assert approval.status_code == 200
    assert approval.json()["status"] == "approved"
    assert approval.json()["decided_by_id"] == str(coordinator.id)
    assert approval.json()["decided_at"] is not None

    db.refresh(request)
    assert request.status is EventStatus.APPROVED
    assert request.decided_by_id == coordinator.id
    # Approval only changes the review decision; it does not allocate any resource.
    assert request.rejection_reason is None


@pytest.mark.story("SCRUM-31")
async def test_rejection_requires_a_reason_and_records_the_decision(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = make_draft(db, organiser)

    async with make_client(organiser) as organiser_client:
        await _submit(organiser_client, request.id)
    request.coordinator_id = coordinator.id
    db.flush()
    async with make_client(coordinator) as coordinator_client:
        missing_reason = await coordinator_client.post(
            f"/api/event-requests/{request.id}/reject", json={"reason": "   "}
        )
        rejected = await coordinator_client.post(
            f"/api/event-requests/{request.id}/reject",
            json={"reason": "Please provide a more accessible venue."},
        )

    assert missing_reason.status_code == 422
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["rejection_reason"] == "Please provide a more accessible venue."
    assert rejected.json()["decided_by_id"] == str(coordinator.id)
    assert rejected.json()["decided_at"] is not None
    db.refresh(request)
    assert request.status is EventStatus.REJECTED
    assert request.decided_by_id == coordinator.id
    assert request.decided_at is not None
    assert request.rejection_reason == "Please provide a more accessible venue."


@pytest.mark.story("SCRUM-31")
async def test_only_a_coordinator_can_review_or_decide(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    async with make_client(organiser) as client:
        assert (await client.get("/api/event-requests/reviewable")).status_code == 403


@pytest.mark.story("SCRUM-31")
async def test_non_assigned_coordinator_can_view_but_cannot_decide_a_request(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    assigned_coordinator = make_user("coordinator")
    other_coordinator = make_user("coordinator")
    request = make_draft(db, organiser)

    async with make_client(organiser) as organiser_client:
        await _submit(organiser_client, request.id)
    request.coordinator_id = assigned_coordinator.id
    db.flush()
    async with make_client(other_coordinator) as other_client:
        read = await other_client.get(f"/api/event-requests/{request.id}")
        approval = await other_client.post(f"/api/event-requests/{request.id}/approve")
        rejection = await other_client.post(
            f"/api/event-requests/{request.id}/reject", json={"reason": "No"}
        )

    assert assigned_coordinator.id == request.coordinator_id
    assert read.status_code == 200
    assert approval.status_code == 403
    assert rejection.status_code == 403
