"""SCRUM-55 AC2-AC6/AC8: coordinator venue search over persisted venues.

Multi-day requested periods (1 Dec 2026 10:00 through 3 Dec 2026 12:00 SGT):
All clock times below are SGT wall-clock; the API stores and compares instants
in UTC, converting to SGT only for the operating-hours check.
    GET /api/venues/search
        Query: start_at=ISO datetime, end_at=ISO datetime,
               minimum_capacity=int, location=str,
               accessibility=str (repeatable), facility=str (repeatable), layout=str
        Auth: Event Coordinator only (-> 403 for other roles, 401 when anonymous).
        Response: 200 with a list of VenueRead (same shape as GET /api/venues),
                  containing only active venues satisfying every criterion,
                  within operating hours on every date, and free of confirmed
                  bookings and unavailability blocks overlapping any part of the
                  period. Pending requests do not block.

Each test names its Test Case ID.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from domain.roles import Role
from domain.venue_booking import BookingStatus
from domain.venue_buffer import VenueBuffers, effective_interval
from models.event_request import EventRequest
from models.organisation import Organisation
from models.user import User
from models.venue import Venue
from models.venue_booking import VenueBooking
from models.venue_unavailability import VenueUnavailability

MakeUser = Callable[..., User]
MakeClient = Callable[[User | None], httpx.AsyncClient]

_SGT = ZoneInfo("Asia/Singapore")

# 1 Dec 2026 10:00 SGT through 3 Dec 2026 12:00 SGT, as UTC instants.
SEARCH_START = "2026-12-01T02:00:00+00:00"
SEARCH_END = "2026-12-03T04:00:00+00:00"


def effective_for(venue: Venue, start_at: datetime, end_at: datetime) -> tuple[datetime, datetime]:
    """SCRUM-82: the stored effective interval, as services.venue_bookings computes it.

    Shared with the other booking test modules, which import it from here as they already
    import `make_venue`.

    Set explicitly rather than defaulted on the model, so a production path that forgets
    it fails loudly instead of silently storing the event period as the occupied one.
    """
    return effective_interval(
        start_at,
        end_at,
        VenueBuffers(
            setup_minutes=venue.setup_minutes, turnaround_minutes=venue.turnaround_minutes
        ),
    )


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
        "start_at": SEARCH_START,
        "end_at": SEARCH_END,
        "minimum_capacity": 100,
        "location": "Level 2, School of Computing",
        "accessibility": "Step-free access",
        "facility": "Projector",
        "layout": "theatre",
    }
    params.update(overrides)
    return params


async def search_as(make_client: MakeClient, user: User, **overrides: Any) -> httpx.Response:
    async with make_client(user) as client:
        return await client.get("/api/venues/search", params=search_params(**overrides))


def result_names(response: httpx.Response) -> list[str]:
    assert response.status_code == 200, response.text
    return [row["name"] for row in response.json()]


def _sgt(day: date, at: time) -> datetime:
    """Combine an SGT calendar date with an SGT wall-clock time."""
    return datetime.combine(day, at, tzinfo=_SGT)


def _make_booking(
    db: Session, venue: Venue, day: date, start: time, end: time, status: BookingStatus
) -> None:
    org = Organisation(name=f"Booking fixture organisation {uuid.uuid4()}")
    db.add(org)
    db.flush()
    organiser = User(
        email=f"{uuid.uuid4()}@example.com",
        password_hash="test",
        roles=[Role.ORGANISER.value],
        organisation_id=org.id,
    )
    coordinator = User(
        email=f"{uuid.uuid4()}@example.com",
        password_hash="test",
        roles=[Role.COORDINATOR.value],
        organisation_id=org.id,
    )
    db.add_all([organiser, coordinator])
    db.flush()
    event = EventRequest(
        organiser_id=organiser.id,
        status=EventStatus.APPROVED,
        start_at=_sgt(day, start),
        end_at=_sgt(day, end),
        coordinator_id=coordinator.id,
    )
    db.add(event)
    db.flush()
    db.add(
        VenueBooking(
            event_request_id=event.id,
            venue_id=venue.id,
            requested_by_id=coordinator.id,
            start_at=_sgt(day, start),
            end_at=_sgt(day, end),
            effective_start_at=effective_for(venue, _sgt(day, start), _sgt(day, end))[0],
            effective_end_at=effective_for(venue, _sgt(day, start), _sgt(day, end))[1],
            status=status,
        )
    )
    db.flush()


def make_confirmed_booking(db: Session, venue: Venue, day: date, start: time, end: time) -> None:
    """A confirmed hold on the venue for [start, end) SGT on day (TC-55-AC4-*)."""
    _make_booking(db, venue, day, start, end, BookingStatus.CONFIRMED)


def make_pending_request(db: Session, venue: Venue, day: date, start: time, end: time) -> None:
    """A pending (not confirmed) request overlapping the slot (TC-55-AC6-01)."""
    _make_booking(db, venue, day, start, end, BookingStatus.PENDING)


def make_unavailability_block(db: Session, venue: Venue, day: date, start: time, end: time) -> None:
    """A recorded unavailability block for [start, end) SGT on day (TC-55-AC5-*)."""
    db.add(
        VenueUnavailability(
            venue_id=venue.id,
            starts_at=_sgt(day, start),
            ends_at=_sgt(day, end),
            reason="maintenance",
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


@pytest.mark.story("SCRUM-55")
async def test_tc55_ac2_05_free_text_criteria_match_case_insensitively(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    make_venue(db, name="Hall A")

    response = await search_as(
        make_client,
        make_user("coordinator"),
        location="level 2, SCHOOL of computing",
        accessibility="STEP-FREE access",
        facility="projector",
        layout="THEATRE",
    )

    assert result_names(response) == ["Hall A"]


# ------------------------------------------------------- TC-55-AC3-01


@pytest.mark.story("SCRUM-55")
async def test_tc55_ac3_01_slot_ending_at_closing_time_is_within_hours(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    make_venue(db, name="Hall A")

    response = await search_as(
        make_client,
        make_user("coordinator"),
        # 1 Dec 20:00 SGT through 3 Dec 22:00 SGT (closing boundary, inclusive).
        start_at="2026-12-01T12:00:00+00:00",
        end_at="2026-12-03T14:00:00+00:00",
    )

    assert result_names(response) == ["Hall A"]


# ------------------------------------------------------- TC-55-AC3-02


@pytest.mark.story("SCRUM-55")
async def test_tc55_ac3_02_slot_ending_after_closing_time_is_excluded(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    make_venue(db, name="Hall A")

    response = await search_as(
        make_client,
        make_user("coordinator"),
        # 1 Dec 20:00 SGT through 3 Dec 22:01 SGT (one minute past closing).
        start_at="2026-12-01T12:00:00+00:00",
        end_at="2026-12-03T14:01:00+00:00",
    )

    assert result_names(response) == []


# ------------------------------------------------------- TC-55-AC4-01


@pytest.mark.story("SCRUM-55")
async def test_tc55_ac4_01_overlapping_confirmed_booking_excludes(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db, name="Hall A")
    make_confirmed_booking(db, venue, date(2026, 12, 2), time(10, 0), time(12, 0))

    response = await search_as(make_client, make_user("coordinator"))

    assert result_names(response) == []


# ------------------------------------------------------- TC-55-AC4-02


@pytest.mark.story("SCRUM-55")
async def test_tc55_ac4_02_adjacent_confirmed_booking_does_not_exclude(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db, name="Hall A")
    make_confirmed_booking(db, venue, date(2026, 12, 1), time(10, 0), time(12, 0))

    response = await search_as(
        make_client,
        make_user("coordinator"),
        # 1 Dec 12:00-14:00 SGT, adjacent to the 10:00-12:00 SGT booking.
        start_at="2026-12-01T04:00:00+00:00",
        end_at="2026-12-01T06:00:00+00:00",
    )

    assert result_names(response) == ["Hall A"]


# ------------------------------------------------------- TC-55-AC5-01


@pytest.mark.story("SCRUM-55")
async def test_tc55_ac5_01_overlapping_unavailability_block_excludes(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db, name="Hall A")
    make_unavailability_block(db, venue, date(2026, 12, 2), time(10, 0), time(12, 0))

    response = await search_as(make_client, make_user("coordinator"))

    assert result_names(response) == []


# ------------------------------------------------------- TC-55-AC5-02


@pytest.mark.story("SCRUM-55")
async def test_tc55_ac5_02_adjacent_unavailability_block_does_not_exclude(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db, name="Hall A")
    make_unavailability_block(db, venue, date(2026, 12, 1), time(10, 0), time(12, 0))

    response = await search_as(
        make_client,
        make_user("coordinator"),
        # 1 Dec 12:00-14:00 SGT, adjacent to the 10:00-12:00 SGT block.
        start_at="2026-12-01T04:00:00+00:00",
        end_at="2026-12-01T06:00:00+00:00",
    )

    assert result_names(response) == ["Hall A"]


# ------------------------------------------------------- TC-55-AC6-01


@pytest.mark.story("SCRUM-55")
async def test_tc55_ac6_01_pending_request_does_not_exclude(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db, name="Hall A")
    make_pending_request(db, venue, date(2026, 12, 2), time(10, 0), time(12, 0))

    response = await search_as(make_client, make_user("coordinator"))

    assert result_names(response) == ["Hall A"]


# ------------------------------------------------------- TC-55-AC8-01


@pytest.mark.story("SCRUM-55")
async def test_tc55_ac8_01_non_coordinator_is_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    make_venue(db, name="Hall A")

    response = await search_as(make_client, make_user("venue_staff"))

    assert response.status_code == 403


# ------------------------------------------------------- TC-55-AC3-06 (API half)


@pytest.mark.story("SCRUM-55")
async def test_tc55_ac3_06_overnight_request_running_through_closed_night_is_excluded(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    make_venue(db, name="Hall A")

    response = await search_as(
        make_client,
        make_user("coordinator"),
        # 3 Dec 21:00 SGT through 4 Dec 08:30 SGT: both endpoints look open but the
        # period runs through the closed night.
        start_at="2026-12-03T13:00:00+00:00",
        end_at="2026-12-04T00:30:00+00:00",
    )

    assert result_names(response) == []


@pytest.mark.story("SCRUM-55")
async def test_tc55_ac3_07_naive_requested_period_is_rejected_with_422(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    make_venue(db, name="Hall A")

    async with make_client(make_user("coordinator")) as client:
        response = await client.get(
            "/api/venues/search",
            params={"start_at": "2026-12-01T10:00:00", "end_at": SEARCH_END},
        )

    assert response.status_code == 422
    assert response.json()["detail"][0]["field"] == "start_at"


@pytest.mark.story("SCRUM-55")
async def test_tc55_ac3_08_inverted_requested_period_is_rejected_with_422(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    make_venue(db, name="Hall A")

    async with make_client(make_user("coordinator")) as client:
        response = await client.get(
            "/api/venues/search",
            params={"start_at": SEARCH_END, "end_at": SEARCH_START},
        )

    assert response.status_code == 422
    assert response.json()["detail"][0]["field"] == "end_at"


# ------------------------------------------- TC-55-AC3-09 / AC2-06: refused periods


@pytest.mark.story("SCRUM-55")
async def test_tc55_ac3_09_a_period_that_has_already_ended_is_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # Nothing can be booked into a slot that is already over, so answering with a list of
    # venues tells the coordinator something untrue. Same rule, and same wording, as the
    # elapsed-closure refusal in SCRUM-62.
    make_venue(db, name="Hall A")

    response = await search_as(
        make_client,
        make_user("coordinator"),
        start_at="2020-03-01T02:00:00+00:00",
        end_at="2020-03-01T06:00:00+00:00",
    )

    assert response.status_code == 422
    assert response.json()["detail"] == [{"field": "end_at", "reason": "must be in the future"}]


@pytest.mark.story("SCRUM-55")
async def test_tc55_ac3_10_a_period_running_now_is_still_searchable(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # The rule is on the end, not the start: a slot that has already begun but has not
    # finished is a legitimate thing to look for.
    make_venue(db, name="Hall A")
    now = datetime.now(UTC)

    response = await search_as(
        make_client,
        make_user("coordinator"),
        start_at=(now - timedelta(hours=1)).isoformat(),
        end_at=(now + timedelta(hours=1)).isoformat(),
    )

    assert response.status_code == 200


@pytest.mark.story("SCRUM-55")
@pytest.mark.parametrize("capacity", [0, -50])
async def test_tc55_ac2_06_a_capacity_below_one_is_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient, capacity: int
) -> None:
    # The form already says min=1; without this the API silently accepted -50 and returned
    # every venue, which reads as "the filter did nothing" rather than "that is not a size".
    make_venue(db, name="Hall A")

    response = await search_as(make_client, make_user("coordinator"), minimum_capacity=capacity)

    assert response.status_code == 422
