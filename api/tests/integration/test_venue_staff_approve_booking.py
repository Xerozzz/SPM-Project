"""SCRUM-75: Venue Staff see what blocks a request and approve it.

The approve route itself is SCRUM-74's. These tests cover what SCRUM-75 adds on top:
the clash shown before approving, and who approved and when being stored.
"""

from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.orm import Session

from domain.venue_booking import BookingStatus
from models.venue_booking import VenueBooking
from models.venue_unavailability import VenueUnavailability
from tests.integration.test_decide_venue_booking import listed, pending_booking
from tests.integration.test_submit_event_request import MakeClient, MakeUser


def clashing_booking(
    db: Session, make_user: MakeUser, booking: VenueBooking, status: BookingStatus
) -> VenueBooking:
    """Another request for the same venue and the same period."""
    other = pending_booking(db, make_user)
    other.venue_id = booking.venue_id
    other.start_at = booking.start_at
    other.end_at = booking.end_at
    other.status = status
    db.flush()
    return other


def closure(db: Session, booking: VenueBooking) -> VenueUnavailability:
    """The venue is closed for the whole requested period."""
    block = VenueUnavailability(
        venue_id=booking.venue_id,
        starts_at=booking.start_at,
        ends_at=booking.end_at,
        reason="Maintenance",
    )
    db.add(block)
    db.flush()
    return block


async def approve(client: httpx.AsyncClient, booking: VenueBooking) -> httpx.Response:
    return await client.post(f"/api/venue-bookings/{booking.id}/approve")


# --------------------------------------------------------------------------- AC1


@pytest.mark.story("SCRUM-75")
async def test_a_pending_request_shows_the_confirmed_booking_it_clashes_with(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    booking = pending_booking(db, make_user)
    confirmed = clashing_booking(db, make_user, booking, BookingStatus.CONFIRMED)

    async with make_client(make_user("venue_staff")) as client:
        response = await client.get("/api/venue-bookings")

    conflict = listed(response, booking)["conflict"]
    assert isinstance(conflict, dict)
    assert conflict["kind"] == "booking"
    assert conflict["id"] == str(confirmed.id)
    assert listed(response, confirmed)["conflict"] is None


@pytest.mark.story("SCRUM-75")
async def test_a_pending_request_shows_the_closure_it_clashes_with(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    booking = pending_booking(db, make_user)
    block = closure(db, booking)

    async with make_client(make_user("venue_staff")) as client:
        response = await client.get("/api/venue-bookings")

    conflict = listed(response, booking)["conflict"]
    assert isinstance(conflict, dict)
    assert conflict["kind"] == "unavailability"
    assert conflict["id"] == str(block.id)


@pytest.mark.story("SCRUM-75")
async def test_another_pending_request_is_not_a_clash(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    booking = pending_booking(db, make_user)
    clashing_booking(db, make_user, booking, BookingStatus.PENDING)

    async with make_client(make_user("venue_staff")) as client:
        response = await client.get("/api/venue-bookings")

    assert listed(response, booking)["conflict"] is None


# --------------------------------------------------------------------------- AC2


@pytest.mark.story("SCRUM-75")
async def test_approving_records_who_approved_and_when(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    booking = pending_booking(db, make_user)
    staff = make_user("venue_staff")
    before = datetime.now(UTC)

    async with make_client(staff) as client:
        response = await approve(client, booking)
        listing = await client.get("/api/venue-bookings")

    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"
    row = listed(listing, booking)
    assert row["status"] == "confirmed"
    assert row["decided_by_id"] == str(staff.id)
    assert row["decision_reason"] is None
    decided_at = datetime.fromisoformat(str(row["decided_at"]))
    assert decided_at.utcoffset() is not None
    assert before <= decided_at <= datetime.now(UTC)


# --------------------------------------------------------------------------- AC3


@pytest.mark.story("SCRUM-75")
async def test_approving_over_a_clash_is_refused_and_names_it(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    booking = pending_booking(db, make_user)
    confirmed = clashing_booking(db, make_user, booking, BookingStatus.CONFIRMED)

    async with make_client(make_user("venue_staff")) as client:
        response = await approve(client, booking)

    assert response.status_code == 409
    assert str(confirmed.id) in response.json()["detail"]
    db.refresh(booking)
    assert booking.status is BookingStatus.PENDING
    assert booking.decided_by_id is None
    assert booking.decided_at is None


# --------------------------------------------------------------------------- AC4


@pytest.mark.story("SCRUM-75")
@pytest.mark.parametrize("role", ["coordinator", "organiser", "tech_support", "attendee"])
async def test_only_venue_staff_may_approve(
    db: Session, make_user: MakeUser, make_client: MakeClient, role: str
) -> None:
    booking = pending_booking(db, make_user)

    async with make_client(make_user(role)) as client:
        response = await approve(client, booking)

    assert response.status_code == 403
    db.refresh(booking)
    assert booking.status is BookingStatus.PENDING
    assert booking.decided_by_id is None


# --------------------------------------------------------------------------- AC5


@pytest.mark.story("SCRUM-75")
async def test_a_rejected_request_cannot_be_approved_and_keeps_its_decision(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    booking = pending_booking(db, make_user)
    first = make_user("venue_staff")
    decided_at = datetime.now(UTC)
    booking.status = BookingStatus.REJECTED
    booking.decided_by_id = first.id
    booking.decided_at = decided_at
    booking.decision_reason = "Hall closed for works"
    db.flush()

    async with make_client(make_user("venue_staff")) as client:
        response = await approve(client, booking)

    assert response.status_code == 409
    db.refresh(booking)
    assert booking.status is BookingStatus.REJECTED
    assert booking.decided_by_id == first.id
    assert booking.decided_at == decided_at
    assert booking.decision_reason == "Hall closed for works"
