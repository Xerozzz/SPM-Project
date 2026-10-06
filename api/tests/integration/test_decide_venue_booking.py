"""SCRUM-40: Venue Staff review pending venue booking requests and reject them."""

import uuid
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.orm import Session

from domain.venue_booking import BookingStatus
from models.event_request import EventRequest
from models.user import User
from models.venue_booking import VenueBooking
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_submit_venue_booking import approved_event, submit
from tests.integration.test_venue_search import make_venue


def pending_booking(db: Session, make_user: MakeUser, **event_changes: object) -> VenueBooking:
    """A pending request from an assigned coordinator for an approved event."""
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator, **event_changes)
    venue = make_venue(db, name=f"Hall {uuid.uuid4()}")
    assert event.start_at is not None and event.end_at is not None
    booking = VenueBooking(
        venue_id=venue.id,
        event_request_id=event.id,
        requested_by_id=coordinator.id,
        start_at=event.start_at,
        end_at=event.end_at,
        status=BookingStatus.PENDING,
    )
    db.add(booking)
    db.flush()
    return booking


async def reject(
    client: httpx.AsyncClient, booking: VenueBooking, reason: str | None = None
) -> httpx.Response:
    body = {} if reason is None else {"reason": reason}
    return await client.post(f"/api/venue-bookings/{booking.id}/reject", json=body)


def listed(response: httpx.Response, booking: VenueBooking) -> dict[str, object]:
    return next(row for row in response.json() if row["id"] == str(booking.id))


# --------------------------------------------------------------------------- AC1


@pytest.mark.story("SCRUM-40")
async def test_venue_staff_see_a_pending_request_with_its_context(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    booking = pending_booking(db, make_user, name="Orientation Day", expected_attendance=150)

    async with make_client(make_user("venue_staff")) as client:
        response = await client.get("/api/venue-bookings")

    assert response.status_code == 200
    row = listed(response, booking)
    assert row["status"] == "pending"
    assert row["venue_id"] == str(booking.venue_id)
    assert str(row["venue_name"]).startswith("Hall ")
    assert row["venue_location"] == "Level 2, School of Computing"
    assert row["event_name"] == "Orientation Day"
    assert datetime.fromisoformat(str(row["start_at"])) == booking.start_at
    assert datetime.fromisoformat(str(row["end_at"])) == booking.end_at
    assert row["expected_attendance"] == 150
    assert row["venue_requirement"] == "Auditorium-type venue"
    assert row["accessibility_requirement"] == "Step-free access and hearing loop"
    assert row["equipment_requirement"] == "Projector-type requirement"
    assert row["layout_requirement"] == "Theatre style"
    assert row["decided_by_id"] is None and row["decided_at"] is None


# --------------------------------------------------------------------------- AC2


@pytest.mark.story("SCRUM-40")
async def test_rejecting_with_a_reason_stores_it(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    booking = pending_booking(db, make_user)

    async with make_client(make_user("venue_staff")) as client:
        response = await reject(client, booking, "Hall closed for renovation")

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    db.refresh(booking)
    assert booking.status is BookingStatus.REJECTED
    assert booking.decision_reason == "Hall closed for renovation"


@pytest.mark.story("SCRUM-40")
@pytest.mark.parametrize("reason", [None, "   "])
async def test_rejecting_without_a_reason_is_allowed(
    db: Session, make_user: MakeUser, make_client: MakeClient, reason: str | None
) -> None:
    booking = pending_booking(db, make_user)

    async with make_client(make_user("venue_staff")) as client:
        response = await reject(client, booking, reason)

    assert response.status_code == 200
    db.refresh(booking)
    assert booking.status is BookingStatus.REJECTED
    assert booking.decision_reason is None


@pytest.mark.story("SCRUM-40")
async def test_a_reason_over_the_limit_is_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    too_long = pending_booking(db, make_user)
    at_limit = pending_booking(db, make_user)

    async with make_client(make_user("venue_staff")) as client:
        refused = await reject(client, too_long, "x" * 1001)
        accepted = await reject(client, at_limit, "x" * 1000)

    assert refused.status_code == 422
    assert accepted.status_code == 200
    db.refresh(too_long)
    assert too_long.status is BookingStatus.PENDING


@pytest.mark.story("SCRUM-40")
async def test_after_rejection_the_coordinator_can_request_again(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # Ties SCRUM-40 to SCRUM-38: a rejection lets the Coordinator keep planning.
    booking = pending_booking(db, make_user)
    coordinator = db.get(User, booking.requested_by_id)
    event = db.get(EventRequest, booking.event_request_id)
    assert coordinator is not None and event is not None

    async with make_client(make_user("venue_staff")) as client:
        await reject(client, booking, "Double-booked offline")
    async with make_client(coordinator) as client:
        again = await submit(client, event, booking.venue_id)

    assert again.status_code == 201
    assert again.json()["status"] == "pending"


# --------------------------------------------------------------------------- AC3


@pytest.mark.story("SCRUM-40")
async def test_a_decision_is_returned_later_with_decider_and_time(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    booking = pending_booking(db, make_user)
    staff = make_user("venue_staff")
    before = datetime.now(UTC)

    async with make_client(staff) as client:
        await reject(client, booking, "No stage available")
        response = await client.get("/api/venue-bookings")

    row = listed(response, booking)
    decided_at = datetime.fromisoformat(str(row["decided_at"]))
    assert row["status"] == "rejected"
    assert row["decided_by_id"] == str(staff.id)
    assert row["decision_reason"] == "No stage available"
    assert decided_at.utcoffset() is not None
    assert before <= decided_at <= datetime.now(UTC)


# --------------------------------------------------------------------------- AC4


@pytest.mark.story("SCRUM-40")
@pytest.mark.parametrize("role", ["coordinator", "organiser", "tech_support", "attendee"])
async def test_only_venue_staff_may_reject(
    db: Session, make_user: MakeUser, make_client: MakeClient, role: str
) -> None:
    booking = pending_booking(db, make_user)

    async with make_client(make_user(role)) as client:
        response = await reject(client, booking, "Not mine to decide")

    assert response.status_code == 403
    db.refresh(booking)
    assert booking.status is BookingStatus.PENDING
    assert booking.decided_by_id is None


@pytest.mark.story("SCRUM-40")
async def test_only_venue_staff_may_list_requests(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("organiser")) as client:
        response = await client.get("/api/venue-bookings")

    assert response.status_code == 403


@pytest.mark.story("SCRUM-40")
async def test_an_unauthenticated_decision_is_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    booking = pending_booking(db, make_user)

    async with make_client(None) as client:
        response = await reject(client, booking)

    assert response.status_code == 401
    db.refresh(booking)
    assert booking.status is BookingStatus.PENDING


@pytest.mark.story("SCRUM-40")
async def test_a_coordinator_who_is_also_venue_staff_may_reject(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # Customer clarification: a Coordinator may also act as the Venue Coordinator.
    booking = pending_booking(db, make_user)

    async with make_client(make_user("coordinator", "venue_staff")) as client:
        response = await reject(client, booking)

    assert response.status_code == 200


# --------------------------------------------------------------------------- AC5


@pytest.mark.story("SCRUM-40")
@pytest.mark.parametrize("decided", [BookingStatus.REJECTED, BookingStatus.CONFIRMED])
async def test_a_decided_request_cannot_be_decided_again(
    db: Session, make_user: MakeUser, make_client: MakeClient, decided: BookingStatus
) -> None:
    booking = pending_booking(db, make_user)
    first = make_user("venue_staff")
    booking.status = decided
    booking.decided_by_id = first.id
    booking.decided_at = datetime.now(UTC)
    booking.decision_reason = "First decision"
    db.flush()

    async with make_client(make_user("venue_staff")) as client:
        response = await reject(client, booking, "Second decision")

    assert response.status_code == 409
    assert str(decided) in response.json()["detail"]
    db.refresh(booking)
    assert booking.status is decided
    assert booking.decided_by_id == first.id
    assert booking.decision_reason == "First decision"


@pytest.mark.story("SCRUM-40")
async def test_an_unknown_request_is_not_found(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("venue_staff")) as client:
        response = await client.post(f"/api/venue-bookings/{uuid.uuid4()}/reject", json={})

    assert response.status_code == 404
