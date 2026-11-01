"""SCRUM-31 AC5: approving or rejecting a request books, reserves and opens nothing.

The review decision only records the outcome. Venue bookings (SCRUM-38), equipment
reservations (SCRUM-53) and registration intake (SCRUM-113) each have their own step.
"""

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.equipment_reservation import EquipmentReservation
from models.event_request import EventRequest
from models.venue_booking import VenueBooking
from tests.integration.test_submit_event_request import MakeClient, MakeUser, make_draft


def allocations(db: Session, event: EventRequest) -> tuple[int, int, object]:
    db.expire_all()
    bookings = db.scalar(
        select(func.count())
        .select_from(VenueBooking)
        .where(VenueBooking.event_request_id == event.id)
    )
    reservations = db.scalar(
        select(func.count())
        .select_from(EquipmentReservation)
        .where(EquipmentReservation.event_request_id == event.id)
    )
    db.refresh(event)
    return bookings or 0, reservations or 0, event.registration_opened_at


async def submitted_and_assigned(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> tuple[EventRequest, httpx.AsyncClient]:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = make_draft(db, organiser)
    async with make_client(organiser) as client:
        response = await client.post(f"/api/event-requests/{request.id}/submit")
    assert response.status_code == 200, response.text
    request.coordinator_id = coordinator.id
    db.flush()
    return request, make_client(coordinator)


@pytest.mark.story("SCRUM-31")
async def test_approval_books_reserves_and_opens_nothing(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    request, coordinator_client = await submitted_and_assigned(db, make_user, make_client)

    async with coordinator_client as client:
        response = await client.post(f"/api/event-requests/{request.id}/approve")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"
    assert allocations(db, request) == (0, 0, None)


@pytest.mark.story("SCRUM-31")
async def test_rejection_books_reserves_and_opens_nothing(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    request, coordinator_client = await submitted_and_assigned(db, make_user, make_client)

    async with coordinator_client as client:
        response = await client.post(
            f"/api/event-requests/{request.id}/reject", json={"reason": "Pick another date."}
        )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "rejected"
    assert allocations(db, request) == (0, 0, None)
