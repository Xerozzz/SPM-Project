"""SCRUM-108: tentative holds expire on their deadline, keep their history, and the
event's assigned Coordinator is notified.

`expire_due_holds` is what the minute timer runs (core/hold_expiry.py). It is called
directly here with a chosen `now`, so no test waits for the clock.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from domain.venue_booking import BookingStatus
from models.event_request import EventRequest
from models.notification import Notification
from models.user import User
from models.venue import Venue
from models.venue_booking import VenueBooking
from services.venue_hold_expiry import expire_due_holds
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_venue_holds import _END, _HOUR, _START, _held, _request
from tests.integration.test_venue_search import make_venue


async def _hold(
    db: Session, make_client: MakeClient, staff: User, coordinator: User, venue: Venue
) -> VenueBooking:
    return await _held(db, make_client, staff, _request(db, coordinator, venue))


def _after_expiry(booking: VenueBooking) -> datetime:
    assert booking.expires_at is not None
    return booking.expires_at + timedelta(seconds=1)


def _notifications(db: Session, booking: VenueBooking) -> list[Notification]:
    statement = select(Notification).where(Notification.source_id == str(booking.id))
    return list(db.scalars(statement))


# --------------------------------------------------------------------------- AC1


@pytest.mark.story("SCRUM-108")
async def test_a_hold_past_its_expiry_becomes_expired(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    held = await _hold(
        db, make_client, make_user("venue_staff"), make_user("coordinator"), make_venue(db)
    )

    expired = expire_due_holds(db, _after_expiry(held))

    assert expired == [held.id]
    db.refresh(held)
    assert held.status is BookingStatus.EXPIRED


@pytest.mark.story("SCRUM-108")
async def test_a_hold_expires_exactly_at_its_expiry(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    held = await _hold(
        db, make_client, make_user("venue_staff"), make_user("coordinator"), make_venue(db)
    )
    assert held.expires_at is not None

    assert expire_due_holds(db, held.expires_at - timedelta(seconds=1)) == []
    assert expire_due_holds(db, held.expires_at) == [held.id]


@pytest.mark.story("SCRUM-108")
async def test_only_tentative_holds_that_ran_out_are_expired(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    staff = make_user("venue_staff")
    venue = make_venue(db)
    running = await _hold(db, make_client, staff, make_user("coordinator"), venue)
    pending = _request(db, make_user("coordinator"), venue)
    confirmed = _request(
        db, make_user("coordinator"), make_venue(db, name="Hall B"), status=BookingStatus.CONFIRMED
    )
    assert running.expires_at is not None

    assert expire_due_holds(db, running.expires_at - timedelta(minutes=1)) == []

    for row, status in (
        (running, BookingStatus.TENTATIVE),
        (pending, BookingStatus.PENDING),
        (confirmed, BookingStatus.CONFIRMED),
    ):
        db.refresh(row)
        assert row.status is status


@pytest.mark.story("SCRUM-108")
async def test_an_expired_hold_no_longer_blocks_the_venue(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    staff = make_user("venue_staff")
    venue = make_venue(db)
    held = await _hold(db, make_client, staff, make_user("coordinator"), venue)
    other = _request(db, make_user("coordinator"), venue, _START + _HOUR, _END + _HOUR)
    expire_due_holds(db, _after_expiry(held))
    params = {
        "venue_id": str(venue.id),
        "start_at": (_START + _HOUR).isoformat(),
        "end_at": (_START + 2 * _HOUR).isoformat(),
        "end_range": (_END + 2 * _HOUR).isoformat(),
    }

    async with make_client(make_user("coordinator")) as client:
        availability = await client.get(
            "/api/venue-calendar/availability",
            params={k: params[k] for k in ("venue_id", "start_at", "end_at")},
        )
        calendar = await client.get(
            "/api/venue-calendar",
            params={
                "venue_id": params["venue_id"],
                "start_at": (_START - _HOUR).isoformat(),
                "end_at": params["end_range"],
            },
        )
    async with make_client(staff) as client:
        approval = await client.post(
            f"/api/venue-bookings/{other.id}/approve",
            json={"expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
        )

    assert availability.json()["available"] is True
    # Like a rejected request, it no longer holds anything, so the calendar leaves it out.
    assert str(held.id) not in {entry["id"] for entry in calendar.json()}
    assert approval.status_code == 200


# --------------------------------------------------------------------------- AC2


@pytest.mark.story("SCRUM-108")
async def test_expiry_keeps_the_hold_history_and_leaves_the_event_alone(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    staff = make_user("venue_staff")
    held = await _hold(db, make_client, staff, make_user("coordinator"), make_venue(db))
    history = (held.venue_id, held.start_at, held.end_at, held.expires_at, held.held_by_id)
    event = db.get(EventRequest, held.event_request_id)
    assert event is not None

    expire_due_holds(db, _after_expiry(held))

    db.refresh(held)
    db.refresh(event)
    assert (held.venue_id, held.start_at, held.end_at, held.expires_at, held.held_by_id) == (
        history
    )
    assert held.held_at is not None
    assert event.status is EventStatus.APPROVED

    async with make_client(staff) as client:
        details = await client.get(f"/api/venue-calendar/bookings/{held.id}")
        listed = await client.get("/api/venue-bookings")
    assert details.json()["status"] == "expired"
    row = next(item for item in listed.json() if item["id"] == str(held.id))
    assert row["status"] == "expired"
    assert row["expires_at"] is not None


@pytest.mark.story("SCRUM-108")
async def test_an_expired_hold_cannot_be_approved_or_held_again(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    staff = make_user("venue_staff")
    held = await _hold(db, make_client, staff, make_user("coordinator"), make_venue(db))
    expire_due_holds(db, _after_expiry(held))

    async with make_client(staff) as client:
        approval = await client.post(
            f"/api/venue-bookings/{held.id}/approve",
            json={"expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
        )
        again = await client.post(
            f"/api/venue-bookings/{held.id}/hold",
            json={"expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
        )

    assert approval.status_code == 409
    assert again.status_code == 409
    db.refresh(held)
    assert held.status is BookingStatus.EXPIRED


@pytest.mark.story("SCRUM-108")
async def test_the_coordinator_can_request_the_venue_again_after_expiry(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    coordinator = make_user("coordinator")
    venue = make_venue(db)
    held = await _hold(db, make_client, make_user("venue_staff"), coordinator, venue)
    expire_due_holds(db, _after_expiry(held))

    async with make_client(coordinator) as client:
        response = await client.post(
            f"/api/event-requests/{held.event_request_id}/venue-bookings",
            json={"venue_id": str(venue.id)},
        )

    assert response.status_code == 201


# --------------------------------------------------------------------------- AC3


@pytest.mark.story("SCRUM-108")
async def test_the_assigned_coordinator_is_notified_when_the_hold_expires(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    coordinator = make_user("coordinator")
    held = await _hold(db, make_client, make_user("venue_staff"), coordinator, make_venue(db))

    expire_due_holds(db, _after_expiry(held))

    async with make_client(coordinator) as client:
        inbox = await client.get("/api/notifications")
    [notification] = [n for n in inbox.json() if n["source_id"] == str(held.id)]
    assert notification["type"] == "venue_hold_expired"
    assert notification["source_type"] == "venue_booking"
    assert notification["event_request_id"] == str(held.event_request_id)
    assert notification["is_unread"] is True
    assert held.expires_at is not None
    assert datetime.fromisoformat(notification["occurred_at"]) == held.expires_at


@pytest.mark.story("SCRUM-108")
async def test_the_coordinator_is_notified_only_once(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    held = await _hold(
        db, make_client, make_user("venue_staff"), make_user("coordinator"), make_venue(db)
    )

    expire_due_holds(db, _after_expiry(held))
    expire_due_holds(db, _after_expiry(held) + timedelta(hours=1))

    assert len(_notifications(db, held)) == 1


@pytest.mark.story("SCRUM-108")
async def test_after_a_reassignment_the_current_coordinator_is_notified(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    first = make_user("coordinator")
    second = make_user("coordinator")
    held = await _hold(db, make_client, make_user("venue_staff"), first, make_venue(db))
    event = db.get(EventRequest, held.event_request_id)
    assert event is not None
    event.coordinator_id = second.id
    db.flush()

    expire_due_holds(db, _after_expiry(held))

    assert [n.recipient_id for n in _notifications(db, held)] == [second.id]


@pytest.mark.story("SCRUM-108")
async def test_nobody_else_sees_the_notification(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    staff = make_user("venue_staff")
    held = await _hold(db, make_client, staff, make_user("coordinator"), make_venue(db))
    expire_due_holds(db, _after_expiry(held))

    for other in (staff, make_user("coordinator"), make_user("organiser")):
        async with make_client(other) as client:
            inbox = await client.get("/api/notifications")
        assert str(held.id) not in {n["source_id"] for n in inbox.json()}


# --------------------------------------------------------------------------- run on writes


@pytest.mark.story("SCRUM-108")
async def test_placing_a_hold_first_expires_holds_that_ran_out(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """Without waiting for the minute timer, a hold that ran out does not block a new one.
    The constraint would refuse the new hold if the old one were still tentative."""
    staff = make_user("venue_staff")
    venue = make_venue(db)
    old = await _hold(db, make_client, staff, make_user("coordinator"), venue)
    old.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.flush()
    new = _request(db, make_user("coordinator"), venue)

    async with make_client(staff) as client:
        response = await client.post(
            f"/api/venue-bookings/{new.id}/hold",
            json={"expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
        )

    assert response.status_code == 200
    db.refresh(old)
    assert old.status is BookingStatus.EXPIRED
    assert len(_notifications(db, old)) == 1


@pytest.mark.story("SCRUM-108")
async def test_approving_first_expires_holds_that_ran_out(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    staff = make_user("venue_staff")
    venue = make_venue(db)
    old = await _hold(db, make_client, staff, make_user("coordinator"), venue)
    old.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.flush()
    other = _request(db, make_user("coordinator"), venue)

    async with make_client(staff) as client:
        response = await client.post(
            f"/api/venue-bookings/{other.id}/approve",
            json={"expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
        )

    assert response.status_code == 200
    db.refresh(old)
    assert old.status is BookingStatus.EXPIRED


@pytest.mark.story("SCRUM-110")
async def test_an_approval_made_hold_expires_like_any_hold(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """TC-110-05: approval IS the hold, so the SCRUM-108 worker expires it and notifies
    the assigned Coordinator exactly once."""
    coordinator = make_user("coordinator")
    venue = make_venue(db)
    request = _request(db, coordinator, venue)
    staff = make_user("venue_staff")

    async with make_client(staff) as client:
        approval = await client.post(
            f"/api/venue-bookings/{request.id}/approve",
            json={"expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
        )
    assert approval.status_code == 200
    db.refresh(request)
    assert request.status is BookingStatus.TENTATIVE
    expiry = request.expires_at
    assert expiry is not None

    assert expire_due_holds(db, expiry + timedelta(seconds=1)) == [request.id]
    expired = db.get(VenueBooking, request.id)
    assert expired is not None and expired.status == BookingStatus.EXPIRED
    assert len(_notifications(db, request)) == 1
