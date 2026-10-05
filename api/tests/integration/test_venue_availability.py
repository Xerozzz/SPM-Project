"""SCRUM-76: the calendar says whether a venue is free for a period."""

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy.orm import Session

from domain.venue_booking import BookingStatus
from models.venue import Venue
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_venue_calendar import _DAY, _HOUR, booking, closure
from tests.integration.test_venue_search import make_venue

# 09:00 to 12:00 UTC on the test day.
_FROM, _TO = _DAY + 9 * _HOUR, _DAY + 12 * _HOUR


async def check(
    client: httpx.AsyncClient,
    venue_id: uuid.UUID,
    start_at: datetime = _FROM,
    end_at: datetime = _TO,
) -> httpx.Response:
    params = {
        "venue_id": str(venue_id),
        "start_at": start_at.isoformat(),
        "end_at": end_at.isoformat(),
    }
    return await client.get("/api/venue-calendar/availability", params=params)


# --------------------------------------------------------------------------- AC1


@pytest.mark.story("SCRUM-76")
async def test_a_confirmed_booking_makes_the_venue_unavailable(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    confirmed = booking(db, make_user, venue, BookingStatus.CONFIRMED, _FROM + _HOUR, _TO + _HOUR)

    async with make_client(make_user("coordinator")) as client:
        response = await check(client, venue.id)

    assert response.status_code == 200
    assert response.json()["available"] is False
    assert [e["id"] for e in response.json()["entries"]] == [str(confirmed.id)]


@pytest.mark.story("SCRUM-76")
async def test_a_closure_makes_the_venue_unavailable(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    closure(db, venue, _FROM - _HOUR, _FROM + _HOUR)

    async with make_client(make_user("venue_staff")) as client:
        response = await check(client, venue.id)

    assert response.json()["available"] is False


# --------------------------------------------------------------------------- AC2


@pytest.mark.story("SCRUM-76")
async def test_a_pending_request_is_shown_but_the_venue_is_still_available(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    pending = booking(db, make_user, venue, BookingStatus.PENDING, _FROM, _TO)

    async with make_client(make_user("coordinator")) as client:
        response = await check(client, venue.id)

    assert response.json()["available"] is True
    assert [(e["id"], e["status"]) for e in response.json()["entries"]] == [
        (str(pending.id), "pending")
    ]


# --------------------------------------------------------------------------- AC3


@pytest.mark.story("SCRUM-76")
async def test_with_nothing_in_the_period_the_venue_is_available(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)

    async with make_client(make_user("venue_staff")) as client:
        response = await check(client, venue.id)

    assert response.json()["available"] is True
    assert response.json()["entries"] == []


@pytest.mark.story("SCRUM-76")
async def test_a_period_outside_opening_hours_is_still_reported_available(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)  # open 08:00 to 22:00 Singapore time

    # 17:00 to 18:00 UTC is 01:00 to 02:00 Singapore time, when the venue is shut.
    async with make_client(make_user("coordinator")) as client:
        response = await check(client, venue.id, _DAY + 17 * _HOUR, _DAY + 18 * _HOUR)

    # Nothing holds it, so it is available. Opening hours are not considered here.
    assert response.status_code == 200
    assert response.json()["available"] is True


@pytest.mark.story("SCRUM-76")
async def test_a_booking_ending_exactly_at_the_start_does_not_block(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """Half-open periods, the same rule as venue search and the conflict check."""
    venue = make_venue(db)
    booking(db, make_user, venue, BookingStatus.CONFIRMED, _FROM - 2 * _HOUR, _FROM)
    closure(db, venue, _TO, _TO + _HOUR)

    async with make_client(make_user("coordinator")) as client:
        response = await check(client, venue.id)

    assert response.json()["available"] is True


@pytest.mark.story("SCRUM-76")
async def test_another_venue_being_booked_does_not_matter(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue, other = make_venue(db, name="Free Hall"), make_venue(db, name="Busy Hall")
    booking(db, make_user, other, BookingStatus.CONFIRMED, _FROM, _TO)

    async with make_client(make_user("coordinator")) as client:
        response = await check(client, venue.id)

    assert response.json()["available"] is True


@pytest.mark.story("SCRUM-76")
async def test_a_deactivated_venue_is_never_available(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db, is_active=False)

    async with make_client(make_user("coordinator")) as client:
        response = await check(client, venue.id)

    assert response.json()["available"] is False


@pytest.mark.story("SCRUM-76")
async def test_the_period_is_answered_in_utc(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    sgt = timezone(timedelta(hours=8))

    async with make_client(make_user("coordinator")) as client:
        response = await check(client, venue.id, _FROM.astimezone(sgt), _TO.astimezone(sgt))

    assert datetime.fromisoformat(response.json()["start_at"]) == _FROM
    assert datetime.fromisoformat(response.json()["start_at"]).utcoffset() == timedelta(0)


@pytest.mark.story("SCRUM-76")
async def test_an_unknown_venue_is_not_found(make_user: MakeUser, make_client: MakeClient) -> None:
    async with make_client(make_user("coordinator")) as client:
        response = await check(client, uuid.uuid4())

    assert response.status_code == 404


@pytest.mark.story("SCRUM-76")
async def test_a_backwards_period_is_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)

    async with make_client(make_user("coordinator")) as client:
        response = await check(client, venue.id, _TO, _FROM)

    assert response.status_code == 422


# --------------------------------------------------------------------------- AC4


@pytest.mark.story("SCRUM-76")
@pytest.mark.parametrize("role", ["organiser", "attendee"])
async def test_organisers_and_attendees_are_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient, role: str
) -> None:
    venue: Venue = make_venue(db)

    async with make_client(make_user(role)) as client:
        response = await check(client, venue.id)

    assert response.status_code == 403
