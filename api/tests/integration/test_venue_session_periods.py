"""SCRUM-111: venue requests carry session labels and independent periods."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from domain.venue_booking import BookingStatus
from models.event_request import EventRequest
from models.user import User
from models.venue_booking import VenueBooking
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_submit_venue_booking import (
    approved_event,
    bookings,
    list_venue_bookings,
    seed_equipment,
    submit,
)
from tests.integration.test_venue_search import make_venue

_HOUR = timedelta(hours=1)


def _confirm_session(db: Session, booking_id: str) -> None:
    """Availability and approval conflicts only see confirmed rows, so flip one."""
    row = db.scalar(select(VenueBooking).where(VenueBooking.id == booking_id))
    assert row is not None
    row.status = BookingStatus.CONFIRMED
    db.flush()


def _session(event: EventRequest, start_offset: int, end_offset: int) -> tuple[str, str]:
    """A session period inside the parent event, as ISO instants."""
    assert event.start_at is not None and event.end_at is not None
    start = event.start_at + start_offset * _HOUR
    end = event.start_at + end_offset * _HOUR
    assert end <= event.end_at
    return start.isoformat(), end.isoformat()


async def _submit_session(
    client: httpx.AsyncClient,
    event: EventRequest,
    venue_id: object,
    label: str,
    start: str,
    end: str,
) -> httpx.Response:
    return await client.post(
        f"/api/event-requests/{event.id}/venue-bookings",
        json={
            "venue_id": str(venue_id),
            "session_label": label,
            "start_at": start,
            "end_at": end,
        },
    )


@pytest.mark.story("US-111")
async def test_labelled_shorter_session_stores_supplied_period(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """TC-111-02: the row keeps the supplied session period, not the parent times."""
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator)
    venue = make_venue(db)
    assert event.start_at is not None and event.end_at is not None
    start, end = _session(event, 1, 2)

    async with make_client(coordinator) as client:
        response = await _submit_session(client, event, venue.id, "Morning workshop", start, end)

    assert response.status_code == 201
    body = response.json()
    assert body["session_label"] == "Morning workshop"
    row = bookings(db)[0]
    assert (row.session_label, row.start_at, row.end_at) == (
        "Morning workshop",
        datetime.fromisoformat(start),
        datetime.fromisoformat(end),
    )
    assert (row.start_at, row.end_at) != (event.start_at, event.end_at)


@pytest.mark.story("US-111")
async def test_parallel_sessions_at_different_venues_stay_independent(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """TC-111-03: overlapping sessions at different venues each stand alone."""
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator)
    first = make_venue(db, name="Hall A")
    second = make_venue(db, name="Hall B")
    start, end = _session(event, 1, 3)

    async with make_client(coordinator) as client:
        one = await _submit_session(client, event, first.id, "Track A", start, end)
        two = await _submit_session(client, event, second.id, "Track B", start, end)
        history = await list_venue_bookings(client, event)

    assert one.status_code == two.status_code == 201
    assert history.status_code == 200
    rows = bookings(db)
    assert len(rows) == 2
    assert [row.session_label for row in rows] == ["Track A", "Track B"]
    assert [item["id"] for item in history.json()] == [one.json()["id"], two.json()["id"]]


@pytest.mark.story("US-111")
async def test_invalid_session_or_wrong_state_creates_no_booking(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """TC-111-04: bad session input and wrong planning state refuse without mutation."""
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator)
    venue = make_venue(db)
    assert event.start_at is not None and event.end_at is not None
    start, end = _session(event, 1, 2)
    outsider = make_user("coordinator")

    async with make_client(coordinator) as client:
        blank = await _submit_session(client, event, venue.id, "   ", start, end)
        reversed_period = await _submit_session(
            client, event, venue.id, "Backwards", end, start
        )
        outside = await _submit_session(
            client,
            event,
            venue.id,
            "Too long",
            (event.start_at - _HOUR).isoformat(),
            end,
        )
    async with make_client(outsider) as client:
        forbidden = await _submit_session(client, event, venue.id, "Track A", start, end)
    async with make_client(None) as client:
        unauthenticated = await _submit_session(client, event, venue.id, "Track A", start, end)

    assert blank.status_code == 422
    assert reversed_period.status_code == 422
    assert outside.status_code == 422
    assert forbidden.status_code == 403
    assert unauthenticated.status_code in (401, 403)
    assert bookings(db) == []


@pytest.mark.story("US-111")
async def test_search_uses_the_session_period_not_the_parent(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """TC-111-05: a venue busy only outside the session period stays available."""
    coordinator = make_user("coordinator")
    event = approved_event(
        db,
        make_user("organiser"),
        coordinator,
        start_at=datetime(2026, 11, 3, 9, 0, tzinfo=UTC),
        end_at=datetime(2026, 11, 3, 13, 0, tzinfo=UTC),
    )
    venue = make_venue(db)
    assert event.start_at is not None and event.end_at is not None
    # Occupy the last hour of the event; the session wants the first hour.
    busy_start = event.end_at - _HOUR
    busy_end = event.end_at
    session_start, session_end = _session(event, 0, 1)

    async with make_client(coordinator) as client:
        held = await _submit_session(
            client,
            event,
            venue.id,
            "Closing plenary",
            busy_start.isoformat(),
            busy_end.isoformat(),
        )
        assert held.status_code == 201

    _confirm_session(db, held.json()["id"])
    async with make_client(coordinator) as client:
        search = await client.get(
            "/api/venues/search",
            params={"start_at": session_start, "end_at": session_end},
        )
        availability = await client.get(
            "/api/venue-calendar/availability",
            params={"venue_id": str(venue.id), "start_at": session_start, "end_at": session_end},
        )

    assert search.status_code == 200
    assert str(venue.id) in [item["id"] for item in search.json()]
    assert availability.status_code == 200
    assert availability.json()["available"] is True


@pytest.mark.story("US-111")
async def test_same_venue_session_overlap_is_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """TC-111-06: overlapping sessions at one venue conflict; other venues stay valid."""
    coordinator = make_user("coordinator")
    staff = make_user("venue_staff")
    event = approved_event(db, make_user("organiser"), coordinator)
    venue = make_venue(db)
    other = make_venue(db, name="Hall B")
    first_start, first_end = _session(event, 1, 3)
    overlap_start, overlap_end = _session(event, 2, 4)

    async with make_client(coordinator) as client:
        first = await _submit_session(client, event, venue.id, "Track A", first_start, first_end)
        assert first.status_code == 201
        parallel = await _submit_session(
            client, event, other.id, "Track B", overlap_start, overlap_end
        )
        assert parallel.status_code == 201

    _confirm_session(db, first.json()["id"])
    async with make_client(staff) as client:
        clash = await client.post(
            f"/api/venue-bookings/{parallel.json()['id']}/approve",
            json={"expires_at": (event.start_at - timedelta(days=1)).isoformat()},
        )
        assert clash.status_code == 200
    async with make_client(coordinator) as client:
        overlapping_same_venue = await _submit_session(
            client, event, venue.id, "Track B", overlap_start, overlap_end
        )
        assert overlapping_same_venue.status_code == 201
    async with make_client(staff) as client:
        refused = await client.post(
            f"/api/venue-bookings/{overlapping_same_venue.json()['id']}/approve",
            json={"expires_at": (event.start_at - timedelta(days=1)).isoformat()},
        )
    assert refused.status_code == 409


@pytest.mark.story("US-111")
async def test_staff_decision_coordinator_list_and_calendar_agree(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """TC-111-07: every read shows the same label and actual period."""
    coordinator = make_user("coordinator")
    staff = make_user("venue_staff")
    event = approved_event(db, make_user("organiser"), coordinator)
    venue = make_venue(db)
    start, end = _session(event, 1, 2)

    async with make_client(coordinator) as client:
        created = await _submit_session(client, event, venue.id, "Morning workshop", start, end)
        assert created.status_code == 201
        booking_id = created.json()["id"]
        listed = await list_venue_bookings(client, event)
    async with make_client(staff) as client:
        queue = await client.get("/api/venue-bookings")
        calendar = await client.get(
            "/api/venue-calendar",
            params={"start_at": event.start_at.isoformat(), "end_at": event.end_at.isoformat()},
        )
        details = await client.get(f"/api/venue-calendar/bookings/{booking_id}")

    assert listed.json()[0]["session_label"] == "Morning workshop"
    queued = [item for item in queue.json() if item["id"] == booking_id][0]
    assert queued["session_label"] == "Morning workshop"
    assert datetime.fromisoformat(queued["start_at"]) == datetime.fromisoformat(start)
    entries = [item for item in calendar.json() if item["id"] == booking_id]
    assert len(entries) == 1
    assert entries[0]["session_label"] == "Morning workshop"
    assert details.json()["session_label"] == "Morning workshop"

    async with make_client(staff) as client:
        rejected = await client.post(
            f"/api/venue-bookings/{booking_id}/reject", json={"reason": "No capacity"}
        )
    assert rejected.status_code == 200
    rows = bookings(db)
    assert len(rows) == 1
    assert rows[0].status is BookingStatus.REJECTED


@pytest.mark.story("US-111")
async def test_suitability_uses_parent_event_requirements(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """TC-111-08: a short session is scored against the event's recorded needs."""
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator, expected_attendance=250)
    seed_equipment(db, event)
    venue = make_venue(
        db,
        maximum_capacity=100,
        facilities=["Microphone"],
        accessibility_features=["Step-free access"],
        supported_layouts=["theatre", "classroom"],
    )
    start, end = _session(event, 1, 2)

    async with make_client(coordinator) as client:
        created = await _submit_session(client, event, venue.id, "Morning workshop", start, end)

    assert created.status_code == 201
    assert created.json()["suitability"]["mismatch_codes"] == ["CAPACITY_EXCEEDED"]


@pytest.mark.story("US-111")
async def test_whole_event_rows_keep_recorded_periods(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """TC-111-09: a whole-event request keeps the parent period beside new sessions."""
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator)
    venue = make_venue(db)
    other = make_venue(db, name="Hall B")
    assert event.start_at is not None and event.end_at is not None
    start, end = _session(event, 1, 2)

    async with make_client(coordinator) as client:
        whole = await submit(client, event, venue.id)
        session = await _submit_session(client, event, other.id, "Morning workshop", start, end)

    assert whole.status_code == session.status_code == 201
    rows = bookings(db)
    assert (rows[0].start_at, rows[0].end_at) == (event.start_at, event.end_at)
    assert (rows[1].start_at, rows[1].end_at) == (
        datetime.fromisoformat(start),
        datetime.fromisoformat(end),
    )
    assert rows[0].session_label != rows[1].session_label

    event.status = EventStatus.CONFIRMED
    db.flush()
    async with make_client(coordinator) as client:
        late = await _submit_session(client, event, other.id, "Late addition", start, end)
    assert late.status_code in (403, 409, 422)
