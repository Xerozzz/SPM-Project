"""SCRUM-38: submit one pending venue request for an approved event."""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from domain.venue_booking import BookingStatus
from models.event_request import EventRequest
from models.user import User
from models.venue_booking import VenueBooking
from tests.integration.test_submit_event_request import MakeClient, MakeUser, make_draft
from tests.integration.test_venue_search import make_venue


def approved_event(
    db: Session, organiser: User, coordinator: User, **changes: object
) -> EventRequest:
    event = make_draft(db, organiser, **changes)
    event.status = EventStatus.APPROVED
    event.coordinator_id = coordinator.id
    db.flush()
    return event


async def submit(
    client: httpx.AsyncClient, event: EventRequest, venue_id: object
) -> httpx.Response:
    return await client.post(
        f"/api/event-requests/{event.id}/venue-bookings", json={"venue_id": str(venue_id)}
    )


def bookings(db: Session) -> list[VenueBooking]:
    return list(db.scalars(select(VenueBooking).order_by(VenueBooking.created_at)))


@pytest.mark.story("SCRUM-38")
async def test_pending_request_keeps_advisory_suitability_and_rejected_history(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator, expected_attendance=250)
    venue = make_venue(
        db,
        maximum_capacity=100,
        facilities=["Microphone"],
        accessibility_features=["Step-free access"],
        supported_layouts=["theatre", "classroom"],
    )

    async with make_client(coordinator) as client:
        preview = await client.get(
            f"/api/event-requests/{event.id}/venue-bookings/suitability",
            params={"venue_id": str(venue.id)},
        )
        created = await submit(client, event, venue.id)
        duplicate = await submit(client, event, venue.id)
        original = bookings(db)[0]
        original.status = BookingStatus.REJECTED
        db.flush()
        resubmitted = await submit(client, event, venue.id)

    suitability = preview.json()
    assert suitability["mismatch_codes"] == ["CAPACITY_EXCEEDED"]
    assert suitability["unavailable_facilities"] == ["Projector"]
    assert suitability["venue_accessibility"] == ["Step-free access"]
    assert suitability["venue_layouts"] == ["theatre", "classroom"]
    assert created.status_code == resubmitted.status_code == 201
    assert created.json() == {"status": "pending", "suitability": suitability}
    assert duplicate.status_code == 409
    assert event.status is EventStatus.APPROVED
    assert (original.event_request_id, original.requested_by_id) == (event.id, coordinator.id)
    assert (original.start_at, original.end_at) == (event.start_at, event.end_at)
    rows = bookings(db)
    assert [row.status for row in rows] == [BookingStatus.REJECTED, BookingStatus.PENDING]
    assert rows[0].id != rows[1].id


@pytest.mark.story("SCRUM-38")
async def test_unauthorised_or_invalid_submission_creates_no_booking(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    coordinator = make_user("coordinator")
    valid = approved_event(db, make_user("organiser"), coordinator)
    start = datetime.now(UTC) + timedelta(days=10)
    invalid = approved_event(
        db,
        make_user("organiser"),
        coordinator,
        venue_requirement=None,
        start_at=start,
        end_at=start - timedelta(hours=1),
    )
    inactive = make_venue(db, is_active=False)

    async with make_client(make_user("coordinator")) as other:
        refused = await submit(other, valid, inactive.id)
    async with make_client(coordinator) as client:
        fields = await submit(client, invalid, uuid.uuid4())
        inactive_response = await submit(client, valid, inactive.id)
        missing = await client.post(f"/api/event-requests/{valid.id}/venue-bookings", json={})

    assert refused.status_code == 403
    assert {item["field"] for item in fields.json()["detail"]} == {
        "venue_requirement",
        "end_at",
        "venue_id",
    }
    assert inactive_response.json()["detail"][0]["field"] == "venue_id"
    assert missing.status_code == 422
    assert missing.json()["detail"][0]["loc"][-1] == "venue_id"
    assert bookings(db) == []
