"""SCRUM-116: the Coordinator starts a linked replacement for an affected arrangement."""

from typing import Any

import httpx
import pytest
from sqlalchemy.orm import Session

from domain.venue_booking import BookingStatus
from models.user import User
from models.venue_booking import VenueBooking
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_submit_venue_booking import approved_event
from tests.integration.test_venue_unavailabilities import (
    body,
    confirm_booking,
    make_venue,
)


async def _affected(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> tuple[VenueBooking, User]:
    """A confirmed booking that a closure now covers, and its assigned Coordinator."""
    venue = make_venue(db)
    booking = confirm_booking(db, venue, make_user, hours_from_anchor=0)
    async with make_client(make_user("venue_staff")) as client:
        closed = await client.post(f"/api/venues/{venue.id}/unavailabilities", json=body())
    assert closed.status_code == 201, closed.text
    coordinator = db.get(User, booking.requested_by_id)
    assert coordinator is not None
    return booking, coordinator


def _replacement(original: VenueBooking, venue_id: object, **changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "venue_id": str(venue_id),
        "session_label": original.session_label,
        "start_at": original.start_at.isoformat(),
        "end_at": original.end_at.isoformat(),
        "replaces_booking_id": str(original.id),
    }
    values.update(changes)
    return values


async def _request(
    client: httpx.AsyncClient, original: VenueBooking, payload: dict[str, Any]
) -> httpx.Response:
    return await client.post(
        f"/api/event-requests/{original.event_request_id}/venue-bookings", json=payload
    )


# --------------------------------------------------------------------------- AC1, AC2, AC3


@pytest.mark.story("SCRUM-116")
async def test_a_replacement_is_a_new_pending_request_linked_to_the_original(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    original, coordinator = await _affected(db, make_user, make_client)
    other = make_venue(db)

    async with make_client(coordinator) as client:
        response = await _request(client, original, _replacement(original, other.id))
        listed = await client.get(f"/api/event-requests/{original.event_request_id}/venue-bookings")

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "pending"
    assert response.json()["replaces_booking_id"] == str(original.id)
    rows = {row["id"]: row for row in listed.json()}
    assert rows[response.json()["id"]]["replaces_booking_id"] == str(original.id)
    # AC3: the original keeps its status and history, nothing is retired yet.
    assert rows[str(original.id)]["status"] == "confirmed"
    assert rows[str(original.id)]["replaces_booking_id"] is None
    db.refresh(original)
    assert original.status == BookingStatus.CONFIRMED


@pytest.mark.story("SCRUM-116")
async def test_an_arrangement_that_needs_nothing_cannot_be_replaced(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    original = confirm_booking(db, venue, make_user, hours_from_anchor=0)
    coordinator = db.get(User, original.requested_by_id)

    async with make_client(coordinator) as client:
        response = await _request(client, original, _replacement(original, make_venue(db).id))

    assert response.status_code == 422
    assert response.json()["detail"] == [
        {"field": "replaces_booking_id", "reason": "does not need a replacement"}
    ]


@pytest.mark.story("SCRUM-116")
async def test_another_events_arrangement_cannot_be_replaced_here(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    original, coordinator = await _affected(db, make_user, make_client)
    assert original.start_at is not None
    mine = approved_event(
        db, coordinator, coordinator, start_at=original.start_at, end_at=original.end_at
    )

    async with make_client(coordinator) as client:
        response = await client.post(
            f"/api/event-requests/{mine.id}/venue-bookings",
            json=_replacement(original, make_venue(db).id),
        )

    assert response.status_code == 422
    assert response.json()["detail"][0]["reason"] == "is not a venue request of this event"


@pytest.mark.story("SCRUM-116")
async def test_the_session_and_period_must_match_the_original(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    original, coordinator = await _affected(db, make_user, make_client)

    async with make_client(coordinator) as client:
        response = await _request(
            client, original, _replacement(original, make_venue(db).id, session_label="Other")
        )

    assert response.status_code == 422
    assert response.json()["detail"] == [
        {"field": "session_label", "reason": "must match the arrangement replaced"}
    ]


# --------------------------------------------------------------------------- AC6


@pytest.mark.story("SCRUM-116")
async def test_one_replacement_at_a_time_and_another_after_a_rejection(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    original, coordinator = await _affected(db, make_user, make_client)

    async with make_client(coordinator) as client:
        first = await _request(client, original, _replacement(original, make_venue(db).id))
        second = await _request(client, original, _replacement(original, make_venue(db).id))
    assert first.status_code == 201, first.text
    assert second.status_code == 422
    assert second.json()["detail"][0]["reason"] == "already has a replacement in progress"

    async with make_client(make_user("venue_staff")) as client:
        rejected = await client.post(
            f"/api/venue-bookings/{first.json()['id']}/reject", json={"reason": "Too small"}
        )
    assert rejected.status_code == 200, rejected.text

    async with make_client(coordinator) as client:
        again = await _request(client, original, _replacement(original, make_venue(db).id))
    assert again.status_code == 201, again.text
    db.refresh(original)
    assert original.status == BookingStatus.CONFIRMED


# --------------------------------------------------------------------------- AC7


@pytest.mark.story("SCRUM-116")
async def test_only_the_assigned_coordinator_can_request_a_replacement(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    original, _ = await _affected(db, make_user, make_client)

    for user in (make_user("coordinator"), make_user("organiser"), make_user("venue_staff")):
        async with make_client(user) as client:
            response = await _request(client, original, _replacement(original, make_venue(db).id))
        assert response.status_code == 403
