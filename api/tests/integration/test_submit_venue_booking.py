"""SCRUM-38/71/78: submit and retrieve venue requests for an approved event."""

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
from services import equipment_requirements
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


def seed_equipment(db: Session, event: EventRequest) -> None:
    """Give the event the requirement row approval would have created (ADR-0033).

    `approved_event` sets the status directly rather than going through
    `services.event_requests.approve`, so it produces an event with the organiser's
    equipment string and no requirement rows, which approval never does. Tests that care
    what the event *needs* opt into the seeding; doing it in the helper itself would hand
    a live "Projector" to all 43 call sites, several of which then add their own and hit
    the one-live-line-per-type index.
    """
    equipment_requirements.seed_from_event(db, event, datetime.now(UTC))
    db.flush()


async def submit(
    client: httpx.AsyncClient,
    event: EventRequest,
    venue_id: object,
    session_label: str = "Opening keynote",
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> httpx.Response:
    """Submit one session request; defaults cover the whole parent event period.

    SCRUM-111: the API takes the session label and period explicitly rather than
    copying the parent event times, so the helper sends them explicitly too.
    """
    assert event.start_at is not None and event.end_at is not None
    return await client.post(
        f"/api/event-requests/{event.id}/venue-bookings",
        json={
            "venue_id": str(venue_id),
            "session_label": session_label,
            "start_at": (start_at or event.start_at).isoformat(),
            "end_at": (end_at or event.end_at).isoformat(),
        },
    )


async def list_venue_bookings(client: httpx.AsyncClient, event: EventRequest) -> httpx.Response:
    return await client.get(f"/api/event-requests/{event.id}/venue-bookings")


def bookings(db: Session) -> list[VenueBooking]:
    return list(db.scalars(select(VenueBooking).order_by(VenueBooking.created_at)))


@pytest.mark.story("SCRUM-38")
async def test_coordinator_can_list_own_approved_bookable_events(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    coordinator = make_user("coordinator")
    other = make_user("coordinator")
    own = approved_event(db, make_user("organiser"), coordinator, name="Own approved")
    approved_event(db, make_user("organiser"), other, name="Someone else's approved")
    submitted = make_draft(db, make_user("organiser"), coordinator_id=coordinator.id)
    submitted.status = EventStatus.SUBMITTED
    db.flush()

    async with make_client(coordinator) as client:
        response = await client.get("/api/event-requests/bookable")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(own.id)]


@pytest.mark.story("SCRUM-38")
async def test_successful_submission_creates_pending_booking_with_id(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator)
    venue = make_venue(db)

    async with make_client(coordinator) as client:
        created = await submit(client, event, venue.id)

    assert created.status_code == 201
    body = created.json()
    row = bookings(db)[0]
    assert body["id"] == str(row.id)
    assert body["venue_id"] == str(row.venue_id)
    assert datetime.fromisoformat(body["start_at"]) == row.start_at
    assert datetime.fromisoformat(body["end_at"]) == row.end_at
    assert body["status"] == "pending"
    assert (row.event_request_id, row.requested_by_id) == (event.id, coordinator.id)
    assert (row.start_at, row.end_at) == (event.start_at, event.end_at)


@pytest.mark.story("SCRUM-71")
async def test_assigned_coordinator_can_retrieve_existing_pending_booking(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator)
    venue = make_venue(db)

    async with make_client(coordinator) as client:
        created = await submit(client, event, venue.id)
        response = await list_venue_bookings(client, event)

    assert created.status_code == 201
    row = bookings(db)[0]
    body = response.json()
    assert response.status_code == 200
    assert len(body) == 1
    assert body[0]["id"] == str(row.id)
    assert body[0]["venue_id"] == str(venue.id)
    assert datetime.fromisoformat(body[0]["start_at"]) == row.start_at
    assert datetime.fromisoformat(body[0]["end_at"]) == row.end_at
    assert body[0]["status"] == "pending"


@pytest.mark.story("SCRUM-71")
async def test_unassigned_coordinator_cannot_retrieve_event_venue_bookings(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    assigned = make_user("coordinator")
    other = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), assigned)
    venue = make_venue(db)

    async with make_client(assigned) as client:
        created = await submit(client, event, venue.id)
    async with make_client(other) as client:
        response = await list_venue_bookings(client, event)

    assert created.status_code == 201
    assert response.status_code == 403


@pytest.mark.story("SCRUM-71")
async def test_rejected_and_pending_booking_history_are_both_returned(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator)
    venue = make_venue(db)

    async with make_client(coordinator) as client:
        original_response = await submit(client, event, venue.id)
        original = bookings(db)[0]
        original.status = BookingStatus.REJECTED
        db.flush()

        resubmitted = await submit(client, event, venue.id)
        response = await list_venue_bookings(client, event)

    assert original_response.status_code == resubmitted.status_code == 201
    assert response.status_code == 200
    rows = bookings(db)
    assert [item["id"] for item in response.json()] == [str(row.id) for row in rows]
    assert [item["status"] for item in response.json()] == ["rejected", "pending"]


@pytest.mark.story("SCRUM-38")
async def test_suitability_warning_remains_advisory(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator, expected_attendance=250)
    # SCRUM-43: suitability reads the maintained requirements, so the event needs the row
    # approval would have given it rather than only the organiser's string.
    seed_equipment(db, event)
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

    suitability = preview.json()
    assert preview.status_code == 200
    assert suitability["mismatch_codes"] == ["CAPACITY_EXCEEDED"]
    assert suitability["unavailable_facilities"] == ["Projector"]
    assert suitability["venue_accessibility"] == ["Step-free access"]
    assert suitability["venue_layouts"] == ["theatre", "classroom"]
    assert created.status_code == 201
    assert created.json()["suitability"] == suitability


@pytest.mark.story("SCRUM-78")
async def test_additional_venue_request_keeps_existing_pending_booking(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator)
    venue = make_venue(db)
    additional_venue = make_venue(db, name="Hall B")

    async with make_client(coordinator) as client:
        first = await submit(client, event, venue.id)
        original = bookings(db)[0]
        original_values = (original.id, original.venue_id, original.start_at, original.end_at)
        additional = await submit(client, event, additional_venue.id)
        history = await list_venue_bookings(client, event)

    assert first.status_code == additional.status_code == 201
    rows = bookings(db)
    assert len(rows) == 2
    assert rows[0].id != rows[1].id
    assert [row.event_request_id for row in rows] == [event.id, event.id]
    assert [row.venue_id for row in rows] == [venue.id, additional_venue.id]
    assert [row.status for row in rows] == [BookingStatus.PENDING, BookingStatus.PENDING]
    assert (rows[0].id, rows[0].venue_id, rows[0].start_at, rows[0].end_at) == original_values
    assert history.status_code == 200
    assert [row["id"] for row in history.json()] == [first.json()["id"], additional.json()["id"]]


@pytest.mark.story("SCRUM-38")
async def test_rejected_request_is_retained_and_resubmission_creates_pending_row(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator)
    venue = make_venue(db)

    async with make_client(coordinator) as client:
        original_response = await submit(client, event, venue.id)

        # SCRUM-40 has not introduced the rejection action yet, so arrange the state
        # directly and prove SCRUM-38 keeps that history when a new request is submitted.
        original = bookings(db)[0]
        original.status = BookingStatus.REJECTED
        db.flush()

        resubmitted = await submit(client, event, venue.id)

    assert original_response.status_code == resubmitted.status_code == 201
    rows = bookings(db)
    assert [row.status for row in rows] == [BookingStatus.REJECTED, BookingStatus.PENDING]
    assert rows[0].id != rows[1].id


@pytest.mark.story("SCRUM-38")
async def test_unassigned_coordinator_is_forbidden(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    assigned = make_user("coordinator")
    other = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), assigned)
    venue = make_venue(db)

    async with make_client(other) as client:
        response = await submit(client, event, venue.id)

    assert response.status_code == 403
    assert bookings(db) == []


@pytest.mark.story("SCRUM-38")
async def test_invalid_or_missing_requirements_create_no_booking(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    coordinator = make_user("coordinator")
    start = datetime.now(UTC) + timedelta(days=10)
    invalid = approved_event(
        db,
        make_user("organiser"),
        coordinator,
        venue_requirement=None,
        start_at=start,
        end_at=start - timedelta(hours=1),
    )
    venue = make_venue(db)

    async with make_client(coordinator) as client:
        invalid_response = await submit(client, invalid, venue.id)
        missing_body = await client.post(
            f"/api/event-requests/{invalid.id}/venue-bookings", json={}
        )

    assert invalid_response.status_code == 422
    assert {item["field"] for item in invalid_response.json()["detail"]} == {
        "venue_requirement",
        "end_at",
    }
    assert missing_body.status_code == 422
    assert missing_body.json()["detail"][0]["loc"][-1] == "venue_id"
    assert bookings(db) == []


@pytest.mark.story("SCRUM-38")
async def test_inactive_or_missing_venue_is_rejected(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator)
    inactive = make_venue(db, is_active=False)

    async with make_client(coordinator) as client:
        inactive_response = await submit(client, event, inactive.id)
        missing_response = await submit(client, event, uuid.uuid4())

    assert inactive_response.status_code == 422
    assert inactive_response.json()["detail"] == [
        {"field": "venue_id", "reason": "must identify an active venue"}
    ]
    assert missing_response.status_code == 422
    assert missing_response.json()["detail"] == [
        {"field": "venue_id", "reason": "does not identify a venue"}
    ]
    assert bookings(db) == []


@pytest.mark.story("SCRUM-38")
async def test_suitability_endpoint_returns_422_for_invalid_request(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator, expected_attendance=None)
    venue = make_venue(db)

    async with make_client(coordinator) as client:
        response = await client.get(
            f"/api/event-requests/{event.id}/venue-bookings/suitability",
            params={"venue_id": str(venue.id)},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == [{"field": "expected_attendance", "reason": "is required"}]
    assert bookings(db) == []


@pytest.mark.story("SCRUM-38")
async def test_successful_submission_does_not_confirm_booking_or_event(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator)
    venue = make_venue(db)

    async with make_client(coordinator) as client:
        response = await submit(client, event, venue.id)

    assert response.status_code == 201
    db.refresh(event)
    row = bookings(db)[0]
    assert event.status is EventStatus.APPROVED
    assert row.status is BookingStatus.PENDING
