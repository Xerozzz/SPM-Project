"""SCRUM-55 AC2-AC6/AC8: coordinator venue search over persisted venues (TDD red phase).

Expected contract to be built (not yet implemented, so every test here fails red):
    GET /api/venues/search
        Query: date=YYYY-MM-DD, start_time=HH:MM, end_time=HH:MM,
               minimum_capacity=int, location=str,
               accessibility=str (repeatable), facility=str (repeatable), layout=str
        Auth: Event Coordinator only (-> 403 for other roles, 401 when anonymous).
        Response: 200 with a list of VenueRead (same shape as GET /api/venues),
                  containing only active venues satisfying every criterion,
                  within operating hours, and free of confirmed bookings and
                  unavailability blocks in the slot. Pending requests do not block.

Each test names its Test Case ID. Helpers `make_confirmed_booking`,
`make_pending_request` and `make_unavailability_block` currently fail with a
TDD-red message: the booking/unavailability models do not exist yet (no booking
tables in alembic/versions/). When they land, replace the bodies with real inserts;
the test bodies themselves must pass unchanged.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, time
from typing import Any

import httpx
import pytest
from sqlalchemy.orm import Session

from models.user import User
from models.venue import Venue
from models.venue_booking import VenueBooking
from models.venue_unavailability import VenueUnavailability

MakeUser = Callable[..., User]
MakeClient = Callable[[User | None], httpx.AsyncClient]

SEARCH_DATE = "2026-12-01"


def make_venue(db: Session, **overrides: Any) -> Venue:
    """A complete active venue; pass field=value to change one (mirrors SCRUM-59)."""
    values: dict[str, Any] = {
        "name": "Hall A",
        "location": "Level 2, School of Computing",
        "maximum_capacity": 200,
        "facilities": ["Projector", "Hearing loop"],
        "supported_layouts": ["theatre", "classroom"],
        "accessibility_features": ["Step-free access"],
        "opens_at": time(8, 0),
        "closes_at": time(22, 0),
    }
    values.update(overrides)
    venue = Venue(**values)
    db.add(venue)
    db.flush()
    return venue


def search_params(**overrides: Any) -> dict[str, Any]:
    """Criteria matching Hall A; pass field=value to change one."""
    params: dict[str, Any] = {
        "date": SEARCH_DATE,
        "start_time": "10:00",
        "end_time": "12:00",
        "minimum_capacity": 100,
        "location": "Level 2, School of Computing",
        "accessibility": "Step-free access",
        "facility": "Projector",
        "layout": "theatre",
    }
    params.update(overrides)
    return params


async def search_as(
    make_client: MakeClient, user: User, **overrides: Any
) -> httpx.Response:
    async with make_client(user) as client:
        return await client.get("/api/venues/search", params=search_params(**overrides))


def result_names(response: httpx.Response) -> list[str]:
    assert response.status_code == 200, response.text
    return [row["name"] for row in response.json()]


def make_confirmed_booking(
    db: Session, venue: Venue, day: date, start: time, end: time
) -> None:
    """A confirmed hold on the venue for [start, end) on day (TC-55-AC4-*)."""
    db.add(
        VenueBooking(
            venue_id=venue.id,
            start_at=datetime.combine(day, start, tzinfo=UTC),
            end_at=datetime.combine(day, end, tzinfo=UTC),
            status="confirmed",
        )
    )
    db.flush()


def make_pending_request(
    db: Session, venue: Venue, day: date, start: time, end: time
) -> None:
    """A pending (not confirmed) request overlapping the slot (TC-55-AC6-01)."""
    db.add(
        VenueBooking(
            venue_id=venue.id,
            start_at=datetime.combine(day, start, tzinfo=UTC),
            end_at=datetime.combine(day, end, tzinfo=UTC),
            status="pending",
        )
    )
    db.flush()


def make_unavailability_block(
    db: Session, venue: Venue, day: date, start: time, end: time
) -> None:
    """A recorded unavailability block for [start, end) on day (TC-55-AC5-*)."""
    db.add(
        VenueUnavailability(
            venue_id=venue.id,
            start_at=datetime.combine(day, start, tzinfo=UTC),
            end_at=datetime.combine(day, end, tzinfo=UTC),
        )
    )
    db.flush()


# ------------------------------------------------------- TC-55-AC2-01


@pytest.mark.story("SCRUM-55")
async def test_tc55_ac2_01_only_active_fully_matching_venue_returned(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    make_venue(db, name="Hall A")
    make_venue(db, name="Hall B", accessibility_features=[])
    make_venue(db, name="Hall C", is_active=False)

    response = await search_as(make_client, make_user("coordinator"))

    assert result_names(response) == ["Hall A"]


# ------------------------------------------------------- TC-55-AC3-01


@pytest.mark.story("SCRUM-55")
async def test_tc55_ac3_01_slot_ending_at_closing_time_is_within_hours(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    make_venue(db, name="Hall A")

    response = await search_as(
        make_client, make_user("coordinator"), start_time="20:00", end_time="22:00"
    )

    assert result_names(response) == ["Hall A"]


# ------------------------------------------------------- TC-55-AC3-02


@pytest.mark.story("SCRUM-55")
async def test_tc55_ac3_02_slot_ending_after_closing_time_is_excluded(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    make_venue(db, name="Hall A")

    response = await search_as(
        make_client, make_user("coordinator"), start_time="20:00", end_time="22:01"
    )

    assert result_names(response) == []


# ------------------------------------------------------- TC-55-AC4-01


@pytest.mark.story("SCRUM-55")
async def test_tc55_ac4_01_overlapping_confirmed_booking_excludes(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db, name="Hall A")
    make_confirmed_booking(db, venue, date(2026, 12, 1), time(10, 0), time(12, 0))

    response = await search_as(
        make_client, make_user("coordinator"), start_time="11:00", end_time="13:00"
    )

    assert result_names(response) == []


# ------------------------------------------------------- TC-55-AC4-02


@pytest.mark.story("SCRUM-55")
async def test_tc55_ac4_02_adjacent_confirmed_booking_does_not_exclude(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db, name="Hall A")
    make_confirmed_booking(db, venue, date(2026, 12, 1), time(10, 0), time(12, 0))

    response = await search_as(
        make_client, make_user("coordinator"), start_time="12:00", end_time="14:00"
    )

    assert result_names(response) == ["Hall A"]


# ------------------------------------------------------- TC-55-AC5-01


@pytest.mark.story("SCRUM-55")
async def test_tc55_ac5_01_overlapping_unavailability_block_excludes(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db, name="Hall A")
    make_unavailability_block(db, venue, date(2026, 12, 1), time(10, 0), time(12, 0))

    response = await search_as(
        make_client, make_user("coordinator"), start_time="11:00", end_time="13:00"
    )

    assert result_names(response) == []


# ------------------------------------------------------- TC-55-AC5-02


@pytest.mark.story("SCRUM-55")
async def test_tc55_ac5_02_adjacent_unavailability_block_does_not_exclude(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db, name="Hall A")
    make_unavailability_block(db, venue, date(2026, 12, 1), time(10, 0), time(12, 0))

    response = await search_as(
        make_client, make_user("coordinator"), start_time="12:00", end_time="14:00"
    )

    assert result_names(response) == ["Hall A"]


# ------------------------------------------------------- TC-55-AC6-01


@pytest.mark.story("SCRUM-55")
async def test_tc55_ac6_01_pending_request_does_not_exclude(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db, name="Hall A")
    make_pending_request(db, venue, date(2026, 12, 1), time(10, 0), time(12, 0))

    response = await search_as(
        make_client, make_user("coordinator"), start_time="11:00", end_time="13:00"
    )

    assert result_names(response) == ["Hall A"]


# ------------------------------------------------------- TC-55-AC8-01


@pytest.mark.story("SCRUM-55")
async def test_tc55_ac8_01_non_coordinator_is_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    make_venue(db, name="Hall A")

    response = await search_as(make_client, make_user("venue_staff"))

    assert response.status_code == 403
