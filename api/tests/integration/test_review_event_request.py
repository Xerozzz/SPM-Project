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
    async with make_client(coordinator) as client:
        review = await client.get("/api/event-requests/review")
        approval = await client.post(f"/api/event-requests/{request.id}/approve")

    assert review.status_code == 200
    item = review.json()[0]
    assert item["id"] == str(request.id)
    assert item["status"] == "submitted"
    assert item["name"] == "Orientation Day"
    assert item["purpose"] == "Welcome new students"
    assert item["venue_requirement"] == "Auditorium, at least 200 seats"
    assert item["equipment_requirement"] == "Projector, two microphones"
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
async def test_rejection_requires_reason_and_organiser_can_amend_and_resubmit_same_request(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = make_draft(db, organiser)
    request_id = str(request.id)

    async with make_client(organiser) as organiser_client:
        await _submit(organiser_client, request.id)
    async with make_client(coordinator) as coordinator_client:
        missing_reason = await coordinator_client.post(
            f"/api/event-requests/{request.id}/reject", json={"reason": "   "}
        )
        rejected = await coordinator_client.post(
            f"/api/event-requests/{request.id}/reject",
            json={"reason": "Please provide a more accessible venue."},
        )
    async with make_client(organiser) as organiser_client:
        mine = await organiser_client.get("/api/event-requests")
        amended = await organiser_client.patch(
            f"/api/event-requests/{request.id}", json={"venue_requirement": "Accessible hall"}
        )
        resubmitted = await organiser_client.post(f"/api/event-requests/{request.id}/submit")

    assert missing_reason.status_code == 422
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["rejection_reason"] == "Please provide a more accessible venue."
    assert rejected.json()["decided_by_id"] == str(coordinator.id)
    assert rejected.json()["decided_at"] is not None
    assert mine.json()[0]["status"] == "rejected"
    assert mine.json()[0]["rejection_reason"] == "Please provide a more accessible venue."
    assert amended.status_code == 200
    assert resubmitted.status_code == 200
    assert resubmitted.json()["id"] == request_id
    assert resubmitted.json()["status"] == "submitted"
    assert resubmitted.json()["rejection_reason"] is None


@pytest.mark.story("SCRUM-30")
async def test_coordinator_can_request_clarification_and_organiser_can_respond(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = make_draft(db, organiser)

    async with make_client(organiser) as organiser_client:
        await _submit(organiser_client, request.id)
    async with make_client(coordinator) as coordinator_client:
        missing_note = await coordinator_client.post(
            f"/api/event-requests/{request.id}/request-clarification", json={"request": " "}
        )
        clarification = await coordinator_client.post(
            f"/api/event-requests/{request.id}/request-clarification",
            json={"request": "Please confirm wheelchair access."},
        )
        queue_after_request = await coordinator_client.get("/api/event-requests/review")
    async with make_client(organiser) as organiser_client:
        mine = await organiser_client.get("/api/event-requests")
        resubmitted = await organiser_client.post(f"/api/event-requests/{request.id}/submit")

    assert missing_note.status_code == 422
    assert clarification.status_code == 200
    assert clarification.json()["status"] == "clarification_requested"
    assert clarification.json()["clarification_request"] == "Please confirm wheelchair access."
    assert clarification.json()["clarification_requested_by_id"] == str(coordinator.id)
    assert clarification.json()["clarification_requested_at"] is not None
    assert queue_after_request.json() == []
    assert mine.json()[0]["clarification_request"] == "Please confirm wheelchair access."
    assert resubmitted.status_code == 200
    assert resubmitted.json()["status"] == "submitted"
    assert resubmitted.json()["clarification_request"] is None


@pytest.mark.story("SCRUM-31")
async def test_only_a_coordinator_can_review_or_decide(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    async with make_client(organiser) as client:
        assert (await client.get("/api/event-requests/review")).status_code == 403
