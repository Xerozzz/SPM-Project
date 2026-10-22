"""SCRUM-54: Coordinators and Venue Staff see what holds a venue across a date range."""

from datetime import UTC, datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy.orm import Session

from domain.venue_booking import BookingStatus
from models.user import User
from models.venue import Venue
from models.venue_booking import VenueBooking
from models.venue_unavailability import VenueUnavailability
from tests.integration.cancelled_rows import cancellation_record
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_submit_venue_booking import approved_event
from tests.integration.test_venue_search import effective_for, make_venue

_DAY = datetime(2030, 3, 4, tzinfo=UTC)
_HOUR = timedelta(hours=1)


def booking(
    db: Session,
    make_user: MakeUser,
    venue: Venue,
    status: BookingStatus,
    start_at: datetime = _DAY + 9 * _HOUR,
    end_at: datetime = _DAY + 11 * _HOUR,
) -> VenueBooking:
    coordinator: User = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator)
    effective_start, effective_end = effective_for(venue, start_at, end_at)
    row = VenueBooking(
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
    db.add(row)
    db.flush()
    return row


def closure(
    db: Session,
    venue: Venue,
    start_at: datetime = _DAY + 13 * _HOUR,
    end_at: datetime = _DAY + 15 * _HOUR,
) -> VenueUnavailability:
    row = VenueUnavailability(
        venue_id=venue.id, starts_at=start_at, ends_at=end_at, reason="Repairs"
    )
    db.add(row)
    db.flush()
    return row


async def calendar(
    client: httpx.AsyncClient, venue: Venue | None, start_at: datetime, end_at: datetime
) -> httpx.Response:
    params = {"start_at": start_at.isoformat(), "end_at": end_at.isoformat()}
    if venue is not None:
        params["venue_id"] = str(venue.id)
    return await client.get("/api/venue-calendar", params=params)


# --------------------------------------------------------------------------- AC1


@pytest.mark.story("SCRUM-54")
@pytest.mark.parametrize("role", ["coordinator", "venue_staff"])
async def test_each_kind_of_entry_is_shown_and_labelled(
    db: Session, make_user: MakeUser, make_client: MakeClient, role: str
) -> None:
    venue = make_venue(db, name="Calendar Hall")
    confirmed = booking(db, make_user, venue, BookingStatus.CONFIRMED)
    pending = booking(
        db, make_user, venue, BookingStatus.PENDING, _DAY + 11 * _HOUR, _DAY + 12 * _HOUR
    )
    block = closure(db, venue)

    async with make_client(make_user(role)) as client:
        response = await calendar(client, venue, _DAY, _DAY + timedelta(days=1))

    assert response.status_code == 200
    assert [(e["id"], e["kind"], e["status"]) for e in response.json()] == [
        (str(confirmed.id), "booking", "confirmed"),
        (str(pending.id), "booking", "pending"),
        (str(block.id), "unavailability", "unavailable"),
    ]
    first = response.json()[0]
    assert first["venue_name"] == "Calendar Hall"
    assert datetime.fromisoformat(first["start_at"]) == confirmed.start_at


@pytest.mark.story("SCRUM-54")
@pytest.mark.parametrize("status", [BookingStatus.REJECTED, BookingStatus.CANCELLED])
async def test_rejected_and_cancelled_requests_are_not_shown(
    db: Session, make_user: MakeUser, make_client: MakeClient, status: BookingStatus
) -> None:
    venue = make_venue(db)
    booking(db, make_user, venue, status)

    async with make_client(make_user("venue_staff")) as client:
        response = await calendar(client, venue, _DAY, _DAY + timedelta(days=1))

    assert response.json() == []


@pytest.mark.story("SCRUM-54")
async def test_only_entries_overlapping_the_range_are_shown(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """Half-open: an entry ending exactly when the range starts is outside it."""
    venue = make_venue(db)
    booking(db, make_user, venue, BookingStatus.PENDING, _DAY - 2 * _HOUR, _DAY)
    inside = booking(db, make_user, venue, BookingStatus.CONFIRMED, _DAY - _HOUR, _DAY + _HOUR)
    closure(db, venue, _DAY + timedelta(days=1), _DAY + timedelta(days=1, hours=2))

    async with make_client(make_user("coordinator")) as client:
        response = await calendar(client, venue, _DAY, _DAY + timedelta(days=1))

    assert [e["id"] for e in response.json()] == [str(inside.id)]


@pytest.mark.story("SCRUM-54")
async def test_without_a_venue_every_venue_is_shown_and_with_one_only_that_venue(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """Customer clarification: one overview, with a filter by venue."""
    first, second = make_venue(db, name="North Hall"), make_venue(db, name="South Hall")
    in_first = booking(db, make_user, first, BookingStatus.CONFIRMED)
    in_second = closure(db, second)

    async with make_client(make_user("coordinator")) as client:
        everything = await calendar(client, None, _DAY, _DAY + timedelta(days=1))
        filtered = await calendar(client, first, _DAY, _DAY + timedelta(days=1))

    ids = {e["id"] for e in everything.json()}
    assert {str(in_first.id), str(in_second.id)} <= ids
    assert [e["id"] for e in filtered.json()] == [str(in_first.id)]


# --------------------------------------------------------------------------- AC2


@pytest.mark.story("SCRUM-54")
async def test_a_venue_with_nothing_in_the_range_has_an_empty_calendar(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)

    async with make_client(make_user("venue_staff")) as client:
        response = await calendar(client, venue, _DAY, _DAY + timedelta(days=1))

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.story("SCRUM-54")
async def test_a_backwards_range_is_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("coordinator")) as client:
        response = await calendar(client, None, _DAY, _DAY - _HOUR)

    assert response.status_code == 422
    assert response.json()["detail"] == [{"field": "end_at", "reason": "must be after the start"}]


@pytest.mark.story("SCRUM-54")
async def test_a_range_without_a_timezone_is_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("coordinator")) as client:
        response = await client.get(
            "/api/venue-calendar",
            params={"start_at": "2030-03-04T00:00:00", "end_at": "2030-03-05T00:00:00"},
        )

    assert response.status_code == 422


# --------------------------------------------------------------------------- AC3


@pytest.mark.story("SCRUM-54")
@pytest.mark.parametrize("role", ["organiser", "attendee"])
async def test_organisers_and_attendees_are_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient, role: str
) -> None:
    venue = make_venue(db)
    closure(db, venue)

    async with make_client(make_user(role)) as client:
        response = await calendar(client, venue, _DAY, _DAY + timedelta(days=1))

    assert response.status_code == 403
    assert "Repairs" not in response.text


@pytest.mark.story("SCRUM-54")
async def test_signed_out_users_are_refused(db: Session, make_client: MakeClient) -> None:
    async with make_client(None) as client:
        response = await calendar(client, None, _DAY, _DAY + timedelta(days=1))

    assert response.status_code == 401


@pytest.mark.story("SCRUM-54")
async def test_a_range_in_singapore_time_is_answered_in_utc(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AGENTS.md: UTC at every layer. A +08:00 range is read as the same instants."""
    venue = make_venue(db)
    confirmed = booking(db, make_user, venue, BookingStatus.CONFIRMED)
    sgt = timezone(timedelta(hours=8))

    async with make_client(make_user("coordinator")) as client:
        response = await calendar(
            client, venue, _DAY.astimezone(sgt), (_DAY + timedelta(days=1)).astimezone(sgt)
        )

    assert [e["id"] for e in response.json()] == [str(confirmed.id)]
    assert datetime.fromisoformat(response.json()[0]["start_at"]).utcoffset() == timedelta(0)
