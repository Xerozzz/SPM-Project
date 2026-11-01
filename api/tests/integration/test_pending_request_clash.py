"""SCRUM-73: the Coordinator sees a clash on a pending request before Venue Staff reject it.

Same arrangement as test_venue_buffer_conflicts: 30 minutes setup, 45 turnaround, and a
confirmed booking from 10:00 to 12:00, which holds the venue from 09:30 to 12:45.
"""

import pytest
from sqlalchemy.orm import Session

from domain.venue_booking import BookingStatus
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_venue_buffer_conflicts import (
    at,
    booking_for,
    buffered_venue,
    closure_for,
)


@pytest.mark.story("SCRUM-73")
async def test_a_pending_request_that_clashes_shows_the_clash_to_the_coordinator(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = buffered_venue(db)
    coordinator = make_user("coordinator")
    confirmed = booking_for(db, coordinator, venue, at(10), at(12))
    request = booking_for(db, coordinator, venue, at(12), at(13), BookingStatus.PENDING)

    async with make_client(coordinator) as client:
        listed = await client.get(f"/api/event-requests/{request.event_request_id}/venue-bookings")

    assert listed.status_code == 200
    [row] = listed.json()
    assert row["status"] == "pending"
    conflict = row["conflict"]
    assert conflict["kind"] == "booking"
    assert conflict["id"] == str(confirmed.id)


@pytest.mark.story("SCRUM-73")
async def test_a_pending_request_with_room_to_spare_shows_no_clash(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = buffered_venue(db)
    coordinator = make_user("coordinator")
    booking_for(db, coordinator, venue, at(10), at(12))
    request = booking_for(db, coordinator, venue, at(14), at(15), BookingStatus.PENDING)

    async with make_client(coordinator) as client:
        listed = await client.get(f"/api/event-requests/{request.event_request_id}/venue-bookings")

    [row] = listed.json()
    assert row["conflict"] is None


@pytest.mark.story("SCRUM-73")
async def test_a_pending_request_that_runs_into_a_closure_shows_the_closure(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = buffered_venue(db)
    coordinator = make_user("coordinator")
    closure_for(db, venue, at(8), at(9.75))
    request = booking_for(db, coordinator, venue, at(10), at(12), BookingStatus.PENDING)

    async with make_client(coordinator) as client:
        listed = await client.get(f"/api/event-requests/{request.event_request_id}/venue-bookings")

    [row] = listed.json()
    assert row["conflict"]["kind"] == "unavailability"
