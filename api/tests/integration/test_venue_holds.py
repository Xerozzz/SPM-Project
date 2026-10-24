"""SCRUM-83: Venue Staff place a tentative hold on a pending venue booking request. The
hold shows as Tentative and blocks overlapping requests until it ends.

Real PostgreSQL throughout, because part of what is under test is the ADR-0002 exclusion
constraint that migration 0021 widens to tentative holds.
"""

import uuid
from datetime import UTC, datetime, timedelta, timezone

import httpx
import pytest
from psycopg.errors import CheckViolation, ExclusionViolation
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from domain.venue_booking import BookingStatus
from models.user import User
from models.venue import Venue
from models.venue_booking import VenueBooking
from models.venue_unavailability import VenueUnavailability
from repositories import venue_availability
from tests.integration.cancelled_rows import cancellation_record
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_submit_venue_booking import approved_event
from tests.integration.test_venue_search import effective_for, make_venue

# Relative to now, so the expiry rules (in the future, not after the event) stay true
# whenever the suite runs. Whole hours keep the arithmetic readable.
_START = (datetime.now(UTC) + timedelta(days=30)).replace(minute=0, second=0, microsecond=0)
_END = _START + timedelta(hours=3)
_HOUR = timedelta(hours=1)


def _request(
    db: Session,
    coordinator: User,
    venue: Venue,
    start_at: datetime = _START,
    end_at: datetime = _END,
    status: BookingStatus = BookingStatus.PENDING,
) -> VenueBooking:
    """A pending request for its own approved event, assigned to `coordinator`."""
    event = approved_event(db, coordinator, coordinator, start_at=start_at, end_at=end_at)
    effective_start, effective_end = effective_for(venue, start_at, end_at)
    booking = VenueBooking(
        venue_id=venue.id,
        event_request_id=event.id,
        requested_by_id=coordinator.id,
        session_label="Opening keynote",
        start_at=start_at,
        end_at=end_at,
        effective_start_at=effective_start,
        effective_end_at=effective_end,
        status=status,
        **cancellation_record(status, coordinator.id),
    )
    db.add(booking)
    db.flush()
    return booking


def _expiry(days: int = 2) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


async def _hold(
    client: httpx.AsyncClient, booking_id: uuid.UUID, expires_at: object
) -> httpx.Response:
    return await client.post(
        f"/api/venue-bookings/{booking_id}/hold", json={"expires_at": expires_at}
    )


async def _held(
    db: Session, make_client: MakeClient, staff: User, booking: VenueBooking
) -> VenueBooking:
    async with make_client(staff) as client:
        response = await _hold(client, booking.id, _expiry())
    assert response.status_code == 200, response.text
    db.refresh(booking)
    return booking


# --------------------------------------------------------------------------- AC1


@pytest.mark.story("SCRUM-83")
async def test_venue_staff_place_a_hold_with_an_expiry_for_the_assigned_coordinator(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    coordinator = make_user("coordinator")
    staff = make_user("venue_staff")
    request = _request(db, coordinator, make_venue(db))
    expires_at = datetime.now(UTC).replace(microsecond=0) + timedelta(days=3)
    before = datetime.now(UTC)

    async with make_client(staff) as client:
        response = await _hold(client, request.id, expires_at.isoformat())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "tentative"
    assert datetime.fromisoformat(body["expires_at"]) == expires_at
    assert body["held_by_id"] == str(staff.id)
    # AC1: the hold is for the event's assigned Coordinator.
    assert body["coordinator_id"] == str(coordinator.id)
    db.refresh(request)
    assert request.status is BookingStatus.TENTATIVE
    assert request.expires_at == expires_at
    assert request.held_by_id == staff.id
    assert request.held_at is not None and before <= request.held_at <= datetime.now(UTC)
    # A hold is not a decision: approval or rejection still records one later.
    assert request.decided_by_id is None


@pytest.mark.story("SCRUM-83")
async def test_an_expiry_in_singapore_time_is_stored_in_utc(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    request = _request(db, make_user("coordinator"), make_venue(db))
    expires_utc = datetime.now(UTC).replace(microsecond=0) + timedelta(days=3)
    in_singapore = expires_utc.astimezone(timezone(timedelta(hours=8)))

    async with make_client(make_user("venue_staff")) as client:
        response = await _hold(client, request.id, in_singapore.isoformat())

    assert response.status_code == 200
    db.refresh(request)
    assert request.expires_at == expires_utc
    assert request.expires_at is not None and request.expires_at.utcoffset() == timedelta(0)


@pytest.mark.story("SCRUM-83")
async def test_an_expiry_exactly_at_the_event_start_is_accepted(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    request = _request(db, make_user("coordinator"), make_venue(db))

    async with make_client(make_user("venue_staff")) as client:
        response = await _hold(client, request.id, _START.isoformat())

    assert response.status_code == 200


@pytest.mark.story("SCRUM-83")
@pytest.mark.parametrize(
    ("expires_at", "reason"),
    [
        ((datetime.now(UTC) - timedelta(minutes=5)).isoformat(), "must be in the future"),
        ((_START + timedelta(minutes=1)).isoformat(), "must not be after the event starts"),
    ],
)
async def test_an_invalid_expiry_is_refused_and_nothing_changes(
    expires_at: str,
    reason: str,
    db: Session,
    make_user: MakeUser,
    make_client: MakeClient,
) -> None:
    request = _request(db, make_user("coordinator"), make_venue(db))

    async with make_client(make_user("venue_staff")) as client:
        response = await _hold(client, request.id, expires_at)

    assert response.status_code == 422
    assert response.json()["detail"] == [{"field": "expires_at", "reason": reason}]
    db.refresh(request)
    assert request.status is BookingStatus.PENDING
    assert request.expires_at is None


@pytest.mark.story("SCRUM-83")
@pytest.mark.parametrize("body", [{}, {"expires_at": "2030-01-01T09:00:00"}])
async def test_a_missing_or_naive_expiry_is_refused_at_the_door(
    body: dict[str, object], db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    request = _request(db, make_user("coordinator"), make_venue(db))

    async with make_client(make_user("venue_staff")) as client:
        response = await client.post(f"/api/venue-bookings/{request.id}/hold", json=body)

    assert response.status_code == 422
    db.refresh(request)
    assert request.status is BookingStatus.PENDING


@pytest.mark.story("SCRUM-83")
@pytest.mark.parametrize(
    "status", [BookingStatus.CONFIRMED, BookingStatus.REJECTED, BookingStatus.CANCELLED]
)
async def test_only_a_pending_request_can_be_held(
    status: BookingStatus, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    request = _request(db, make_user("coordinator"), make_venue(db), status=status)

    async with make_client(make_user("venue_staff")) as client:
        response = await _hold(client, request.id, _expiry())

    assert response.status_code == 409
    db.refresh(request)
    assert request.status is status
    assert request.expires_at is None


@pytest.mark.story("SCRUM-83")
async def test_a_hold_cannot_be_placed_twice(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    staff = make_user("venue_staff")
    request = await _held(
        db, make_client, staff, _request(db, make_user("coordinator"), make_venue(db))
    )
    first_expiry = request.expires_at

    async with make_client(staff) as client:
        response = await _hold(client, request.id, _expiry(days=5))

    assert response.status_code == 409
    db.refresh(request)
    assert request.expires_at == first_expiry


@pytest.mark.story("SCRUM-83")
@pytest.mark.parametrize("role", ["coordinator", "organiser", "coordinator_lead", "attendee"])
async def test_only_venue_staff_may_place_a_hold(
    role: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    coordinator = make_user("coordinator")
    request = _request(db, coordinator, make_venue(db))
    caller = coordinator if role == "coordinator" else make_user(role)

    async with make_client(caller) as client:
        response = await _hold(client, request.id, _expiry())

    assert response.status_code == 403
    db.refresh(request)
    assert request.status is BookingStatus.PENDING


@pytest.mark.story("SCRUM-83")
async def test_a_signed_out_user_may_not_place_a_hold(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    request = _request(db, make_user("coordinator"), make_venue(db))

    async with make_client(None) as client:
        response = await _hold(client, request.id, _expiry())

    assert response.status_code == 401


@pytest.mark.story("SCRUM-83")
async def test_holding_an_unknown_request_is_not_found(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("venue_staff")) as client:
        response = await _hold(client, uuid.uuid4(), _expiry())

    assert response.status_code == 404


# --------------------------------------------------------------------------- AC2


@pytest.mark.story("SCRUM-83")
async def test_the_calendar_shows_the_hold_as_tentative_with_its_expiry(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    staff = make_user("venue_staff")
    held = await _held(db, make_client, staff, _request(db, make_user("coordinator"), venue))
    confirmed = _request(
        db,
        make_user("coordinator"),
        venue,
        _END + 2 * _HOUR,
        _END + 4 * _HOUR,
        BookingStatus.CONFIRMED,
    )
    params = {
        "start_at": (_START - _HOUR).isoformat(),
        "end_at": (_END + 5 * _HOUR).isoformat(),
        "venue_id": str(venue.id),
    }

    async with make_client(staff) as client:
        calendar = await client.get("/api/venue-calendar", params=params)
        details = await client.get(f"/api/venue-calendar/bookings/{held.id}")

    assert calendar.status_code == 200
    by_id = {entry["id"]: entry for entry in calendar.json()}
    assert by_id[str(held.id)]["status"] == "tentative"
    assert by_id[str(confirmed.id)]["status"] == "confirmed"
    assert held.expires_at is not None
    assert datetime.fromisoformat(by_id[str(held.id)]["expires_at"]) == held.expires_at
    assert by_id[str(confirmed.id)]["expires_at"] is None
    assert details.status_code == 200
    assert details.json()["status"] == "tentative"
    assert datetime.fromisoformat(details.json()["expires_at"]) == held.expires_at


@pytest.mark.story("SCRUM-83")
async def test_booking_views_show_the_hold_as_tentative(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    coordinator = make_user("coordinator")
    staff = make_user("venue_staff")
    held = await _held(db, make_client, staff, _request(db, coordinator, make_venue(db)))

    async with make_client(staff) as client:
        decisions = await client.get("/api/venue-bookings")
    async with make_client(coordinator) as client:
        event_bookings = await client.get(
            f"/api/event-requests/{held.event_request_id}/venue-bookings"
        )

    # Venue Staff's booking view.
    row = next(item for item in decisions.json() if item["id"] == str(held.id))
    assert row["status"] == "tentative"
    assert row["expires_at"] is not None
    # The Coordinator's view of their own event's bookings.
    assert event_bookings.status_code == 200
    [own] = event_bookings.json()
    assert own["status"] == "tentative"
    assert held.expires_at is not None
    assert datetime.fromisoformat(own["expires_at"]) == held.expires_at


# --------------------------------------------------------------------------- AC3


@pytest.mark.story("SCRUM-83")
async def test_a_hold_blocks_approving_an_overlapping_request(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    staff = make_user("venue_staff")
    held = await _held(db, make_client, staff, _request(db, make_user("coordinator"), venue))
    other = _request(db, make_user("coordinator"), venue, _START + _HOUR, _END + _HOUR)

    async with make_client(staff) as client:
        listed = await client.get("/api/venue-bookings")
        approval = await client.post(
            f"/api/venue-bookings/{other.id}/approve", json={"expires_at": _expiry()}
        )

    # The pending card already says why it cannot be approved, and names the hold.
    row = next(item for item in listed.json() if item["id"] == str(other.id))
    assert row["conflict"]["kind"] == "hold"
    assert row["conflict"]["id"] == str(held.id)
    assert approval.status_code == 409
    assert approval.json()["detail"] == f"conflicts with tentative hold {held.id}"
    db.refresh(other)
    assert other.status is BookingStatus.PENDING


@pytest.mark.story("SCRUM-83")
async def test_a_hold_blocks_holding_an_overlapping_request(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    staff = make_user("venue_staff")
    held = await _held(db, make_client, staff, _request(db, make_user("coordinator"), venue))
    other = _request(db, make_user("coordinator"), venue)

    async with make_client(staff) as client:
        response = await _hold(client, other.id, _expiry())

    assert response.status_code == 409
    assert response.json()["detail"] == f"conflicts with tentative hold {held.id}"
    db.refresh(other)
    assert other.status is BookingStatus.PENDING


@pytest.mark.story("SCRUM-83")
async def test_a_hold_is_refused_over_a_confirmed_booking(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    confirmed = _request(db, make_user("coordinator"), venue, status=BookingStatus.CONFIRMED)
    request = _request(db, make_user("coordinator"), venue)

    async with make_client(make_user("venue_staff")) as client:
        response = await _hold(client, request.id, _expiry())

    assert response.status_code == 409
    assert response.json()["detail"] == f"conflicts with confirmed booking {confirmed.id}"
    db.refresh(request)
    assert request.status is BookingStatus.PENDING


@pytest.mark.story("SCRUM-83")
async def test_a_hold_is_refused_over_a_venue_closure(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    closure = VenueUnavailability(
        venue_id=venue.id, starts_at=_START, ends_at=_START + _HOUR, reason="Maintenance"
    )
    db.add(closure)
    db.flush()
    request = _request(db, make_user("coordinator"), venue)

    async with make_client(make_user("venue_staff")) as client:
        response = await _hold(client, request.id, _expiry())

    assert response.status_code == 409
    db.refresh(request)
    assert request.status is BookingStatus.PENDING


@pytest.mark.story("SCRUM-83")
async def test_a_hold_does_not_block_a_request_that_only_touches_it(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    staff = make_user("venue_staff")
    await _held(db, make_client, staff, _request(db, make_user("coordinator"), venue))
    after = _request(db, make_user("coordinator"), venue, _END, _END + _HOUR)

    async with make_client(staff) as client:
        approval = await client.post(
            f"/api/venue-bookings/{after.id}/approve", json={"expires_at": _expiry()}
        )

    # Half-open, as for confirmed bookings: ending exactly as the next starts is no clash.
    assert approval.status_code == 200


@pytest.mark.story("SCRUM-83")
async def test_a_hold_keeps_the_venues_turnaround(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db, turnaround_minutes=60)
    staff = make_user("venue_staff")
    await _held(db, make_client, staff, _request(db, make_user("coordinator"), venue))
    # Starts 30 minutes after the held event ends, inside the hour of turnaround.
    soon_after = _request(db, make_user("coordinator"), venue, _END + _HOUR / 2, _END + 2 * _HOUR)

    async with make_client(staff) as client:
        approval = await client.post(
            f"/api/venue-bookings/{soon_after.id}/approve", json={"expires_at": _expiry()}
        )

    assert approval.status_code == 409


@pytest.mark.story("SCRUM-83")
async def test_another_pending_request_does_not_stop_a_hold(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    _request(db, make_user("coordinator"), venue)
    request = _request(db, make_user("coordinator"), venue)

    async with make_client(make_user("venue_staff")) as client:
        response = await _hold(client, request.id, _expiry())

    assert response.status_code == 200


@pytest.mark.story("SCRUM-83")
async def test_a_held_venue_is_left_out_of_search_and_reported_unavailable(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    staff = make_user("venue_staff")
    await _held(db, make_client, staff, _request(db, make_user("coordinator"), venue))
    params = {
        "venue_id": str(venue.id),
        "start_at": (_START + _HOUR).isoformat(),
        "end_at": (_START + 2 * _HOUR).isoformat(),
    }

    blocked_for_search = venue_availability.venue_ids_with_confirmed_overlap(
        db, _START + _HOUR, _START + 2 * _HOUR
    )
    async with make_client(make_user("coordinator")) as client:
        availability = await client.get("/api/venue-calendar/availability", params=params)

    assert venue.id in blocked_for_search
    assert availability.status_code == 200
    assert availability.json()["available"] is False


@pytest.mark.story("SCRUM-83")
def test_the_database_refuses_an_overlapping_hold_that_skips_the_check(
    db: Session, make_user: MakeUser
) -> None:
    """ADR-0002: the constraint, not the friendly check, is what guarantees AC3. Two
    holds written straight to the table, as two racing requests could, cannot both
    stand."""
    venue = make_venue(db)
    staff = make_user("venue_staff")
    first = _request(db, make_user("coordinator"), venue)
    second = _request(db, make_user("coordinator"), venue)
    for row in (first, second):
        row.status = BookingStatus.TENTATIVE
        row.expires_at = _START - timedelta(days=1)
        row.held_by_id = staff.id
        row.held_at = datetime.now(UTC)

    with pytest.raises(IntegrityError) as refused:
        db.flush()

    assert isinstance(refused.value.orig, ExclusionViolation)
    db.rollback()


@pytest.mark.story("SCRUM-83")
def test_the_database_refuses_a_hold_without_its_expiry(db: Session, make_user: MakeUser) -> None:
    request = _request(db, make_user("coordinator"), make_venue(db))
    request.status = BookingStatus.TENTATIVE

    with pytest.raises(IntegrityError) as refused:
        db.flush()

    assert isinstance(refused.value.orig, CheckViolation)
    db.rollback()
