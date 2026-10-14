"""SCRUM-107: a tentative hold is confirmed through the normal approval, before it expires.

Uses the same approve route as a pending request (SCRUM-74), so the row lock, the
SCRUM-73 conflict check and the overlap constraint all apply unchanged.
"""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.orm import Session

from domain.venue_booking import BookingStatus
from models.user import User
from models.venue import Venue
from models.venue_booking import VenueBooking
from models.venue_unavailability import VenueUnavailability
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_venue_holds import _END, _HOUR, _START, _held, _request
from tests.integration.test_venue_search import make_venue


async def _approve(client: httpx.AsyncClient, booking_id: uuid.UUID) -> httpx.Response:
    return await client.post(f"/api/venue-bookings/{booking_id}/approve")


async def _active_hold(
    db: Session, make_client: MakeClient, staff: User, coordinator: User
) -> VenueBooking:
    return await _held(db, make_client, staff, _request(db, coordinator, make_venue(db)))


# --------------------------------------------------------------------------- AC1


@pytest.mark.story("SCRUM-107")
async def test_approving_an_active_hold_confirms_it_for_the_same_venue_and_period(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    staff = make_user("venue_staff")
    held = await _active_hold(db, make_client, staff, make_user("coordinator"))
    venue_id, start_at, end_at = held.venue_id, held.start_at, held.end_at
    before = datetime.now(UTC)

    async with make_client(staff) as client:
        response = await _approve(client, held.id)

    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"
    db.refresh(held)
    assert held.status is BookingStatus.CONFIRMED
    assert (held.venue_id, held.start_at, held.end_at) == (venue_id, start_at, end_at)
    # Recorded as a normal approval (SCRUM-75 AC2).
    assert held.decided_by_id == staff.id
    assert held.decided_at is not None and before <= held.decided_at <= datetime.now(UTC)


@pytest.mark.story("SCRUM-107")
async def test_a_confirmed_hold_keeps_its_hold_history(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    staff = make_user("venue_staff")
    held = await _active_hold(db, make_client, staff, make_user("coordinator"))
    history = (held.expires_at, held.held_by_id, held.held_at)

    async with make_client(staff) as client:
        assert (await _approve(client, held.id)).status_code == 200

    # AC3: who held it, when, and until when, are all still there.
    db.refresh(held)
    assert (held.expires_at, held.held_by_id, held.held_at) == history
    assert None not in history


@pytest.mark.story("SCRUM-107")
async def test_the_confirmed_hold_shows_as_confirmed_everywhere(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    staff = make_user("venue_staff")
    coordinator = make_user("coordinator")
    held = await _active_hold(db, make_client, staff, coordinator)

    async with make_client(staff) as client:
        assert (await _approve(client, held.id)).status_code == 200
        listed = await client.get("/api/venue-bookings")
        details = await client.get(f"/api/venue-calendar/bookings/{held.id}")
    async with make_client(coordinator) as client:
        own = await client.get(f"/api/event-requests/{held.event_request_id}/venue-bookings")

    row = next(item for item in listed.json() if item["id"] == str(held.id))
    assert row["status"] == "confirmed"
    assert details.json()["status"] == "confirmed"
    assert own.json()[0]["status"] == "confirmed"


@pytest.mark.story("SCRUM-107")
async def test_after_confirmation_the_venue_stays_blocked(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    staff = make_user("venue_staff")
    held = await _active_hold(db, make_client, staff, make_user("coordinator"))
    venue = db.get(Venue, held.venue_id)
    assert venue is not None
    other = _request(db, make_user("coordinator"), venue, _START + _HOUR, _END + _HOUR)

    async with make_client(staff) as client:
        assert (await _approve(client, held.id)).status_code == 200
        refused = await _approve(client, other.id)

    assert refused.status_code == 409
    assert refused.json()["detail"] == f"conflicts with confirmed booking {held.id}"


# --------------------------------------------------------------------------- AC2


@pytest.mark.story("SCRUM-107")
async def test_an_expired_hold_cannot_be_approved_and_is_left_as_it_was(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    staff = make_user("venue_staff")
    held = await _active_hold(db, make_client, staff, make_user("coordinator"))
    # The hold ran out. Set directly, because the API refuses an expiry in the past.
    held.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.flush()

    async with make_client(staff) as client:
        response = await _approve(client, held.id)

    assert response.status_code == 409
    assert response.json()["detail"].startswith("the tentative hold expired at")
    db.refresh(held)
    assert held.status is BookingStatus.TENTATIVE
    assert held.decided_by_id is None and held.decided_at is None


# --------------------------------------------------------------------------- the normal flow


@pytest.mark.story("SCRUM-107")
async def test_a_hold_with_a_clash_cannot_be_approved(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    staff = make_user("venue_staff")
    held = await _active_hold(db, make_client, staff, make_user("coordinator"))
    # A closure recorded after the hold was placed (SCRUM-62 does not check bookings).
    closure = VenueUnavailability(
        venue_id=held.venue_id, starts_at=_START, ends_at=_START + _HOUR, reason="Repairs"
    )
    db.add(closure)
    db.flush()

    async with make_client(staff) as client:
        listed = await client.get("/api/venue-bookings")
        response = await _approve(client, held.id)

    # The panel already shows the clash on the hold, as it does for a pending request.
    row = next(item for item in listed.json() if item["id"] == str(held.id))
    assert row["conflict"]["kind"] == "unavailability"
    assert response.status_code == 409
    db.refresh(held)
    assert held.status is BookingStatus.TENTATIVE


@pytest.mark.story("SCRUM-107")
async def test_a_hold_cannot_be_confirmed_twice(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    staff = make_user("venue_staff")
    held = await _active_hold(db, make_client, staff, make_user("coordinator"))

    async with make_client(staff) as client:
        first = await _approve(client, held.id)
        second = await _approve(client, held.id)

    assert first.status_code == 200
    assert second.status_code == 409


@pytest.mark.story("SCRUM-107")
@pytest.mark.parametrize("role", ["coordinator", "organiser", "coordinator_lead", "attendee"])
async def test_only_venue_staff_may_confirm_a_hold(
    role: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    held = await _active_hold(db, make_client, make_user("venue_staff"), make_user("coordinator"))

    async with make_client(make_user(role)) as client:
        response = await _approve(client, held.id)

    assert response.status_code == 403
    db.refresh(held)
    assert held.status is BookingStatus.TENTATIVE


@pytest.mark.story("SCRUM-107")
async def test_a_pending_request_is_still_approved_as_before(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    staff = make_user("venue_staff")
    request = _request(db, make_user("coordinator"), make_venue(db))

    async with make_client(staff) as client:
        response = await _approve(client, request.id)

    assert response.status_code == 200
    db.refresh(request)
    assert request.status is BookingStatus.CONFIRMED
    assert request.expires_at is None
