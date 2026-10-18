"""SCRUM-77: opening a calendar entry shows what is holding the venue and when.

Event details come from GET /api/event-requests/{id}, which applies
require_event_access(VIEW). These tests check that endpoint answers each role as AC2
and AC3 expect, alongside the entry details themselves.
"""

import uuid
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from domain.venue_booking import BookingStatus
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_venue_calendar import booking, closure
from tests.integration.test_venue_search import make_venue

# --------------------------------------------------------------------------- AC1


@pytest.mark.story("SCRUM-77")
@pytest.mark.parametrize("role", ["coordinator", "venue_staff"])
async def test_a_booking_entry_shows_venue_times_and_status(
    db: Session, make_user: MakeUser, make_client: MakeClient, role: str
) -> None:
    venue = make_venue(db, name="Detail Hall", location="Level 3")
    row = booking(db, make_user, venue, BookingStatus.CONFIRMED)

    async with make_client(make_user(role)) as client:
        response = await client.get(f"/api/venue-calendar/bookings/{row.id}")

    assert response.status_code == 200
    body = response.json()
    assert (body["kind"], body["status"]) == ("booking", "confirmed")
    assert (body["venue_name"], body["venue_location"]) == ("Detail Hall", "Level 3")
    assert datetime.fromisoformat(body["start_at"]) == row.start_at
    assert datetime.fromisoformat(body["end_at"]) == row.end_at
    assert body["event_request_id"] == str(row.event_request_id)
    assert body["reason"] is None


@pytest.mark.story("SCRUM-77")
async def test_a_closure_entry_shows_its_reason(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    block = closure(db, venue)

    async with make_client(make_user("venue_staff")) as client:
        response = await client.get(f"/api/venue-calendar/unavailabilities/{block.id}")

    body = response.json()
    assert (body["kind"], body["status"], body["reason"]) == (
        "unavailability",
        "unavailable",
        "Repairs",
    )
    assert body["event_request_id"] is None
    assert datetime.fromisoformat(body["start_at"]) == block.starts_at


@pytest.mark.story("SCRUM-77")
@pytest.mark.parametrize("kind", ["bookings", "unavailabilities"])
async def test_an_unknown_entry_is_not_found(
    make_user: MakeUser, make_client: MakeClient, kind: str
) -> None:
    async with make_client(make_user("coordinator")) as client:
        response = await client.get(f"/api/venue-calendar/{kind}/{uuid.uuid4()}")

    assert response.status_code == 404


@pytest.mark.story("SCRUM-77")
@pytest.mark.parametrize("role", ["organiser", "attendee"])
async def test_organisers_and_attendees_cannot_open_entries(
    db: Session, make_user: MakeUser, make_client: MakeClient, role: str
) -> None:
    row = booking(db, make_user, make_venue(db), BookingStatus.PENDING)

    async with make_client(make_user(role)) as client:
        response = await client.get(f"/api/venue-calendar/bookings/{row.id}")

    assert response.status_code == 403


# --------------------------------------------------------------------------- AC2 and AC3


@pytest.mark.story("SCRUM-77")
async def test_a_coordinator_sees_the_entry_but_not_unassigned_event_details(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    row = booking(db, make_user, make_venue(db), BookingStatus.CONFIRMED)

    async with make_client(make_user("coordinator")) as client:
        entry = await client.get(f"/api/venue-calendar/bookings/{row.id}")
        event = await client.get(f"/api/event-requests/{entry.json()['event_request_id']}")

    # SCRUM-104: the calendar entry itself stays visible, but the event details belong
    # to the assigned coordinator — this viewer holds no assignment, so no disclosure.
    assert entry.status_code == 200
    assert event.status_code == 403
    assert event.json() == {"detail": "Forbidden"}


@pytest.mark.story("SCRUM-77")
async def test_venue_staff_see_the_entry_but_not_the_events_details(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """Today require_event_access(VIEW) does not let Venue Staff view an event, so the
    entry still shows venue, times and status, and the event details are refused."""
    row = booking(db, make_user, make_venue(db), BookingStatus.CONFIRMED)

    async with make_client(make_user("venue_staff")) as client:
        entry = await client.get(f"/api/venue-calendar/bookings/{row.id}")
        event = await client.get(f"/api/event-requests/{entry.json()['event_request_id']}")

    assert entry.status_code == 200
    assert entry.json()["status"] == "confirmed"
    assert event.status_code == 403
