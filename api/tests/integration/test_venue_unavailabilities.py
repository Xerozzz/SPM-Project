"""SCRUM-62 API evidence for independently achievable closure management."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy.orm import Session

from domain.venue_booking import BookingStatus
from models.user import User
from models.venue import Venue
from models.venue_booking import VenueBooking
from models.venue_unavailability import VenueUnavailability
from tests.integration.test_submit_venue_booking import approved_event
from tests.integration.test_venue_search import effective_for

MakeUser = Callable[..., User]
MakeClient = Callable[[User | None], httpx.AsyncClient]


def make_venue(db: Session, *, is_active: bool = True) -> Venue:
    venue = Venue(
        name=f"Hall {uuid.uuid4()}",
        location="SCIS",
        maximum_capacity=100,
        facilities=[],
        supported_layouts=["theatre"],
        accessibility_features=[],
        opens_at="08:00:00",
        closes_at="22:00:00",
        is_active=is_active,
    )
    db.add(venue)
    db.flush()
    return venue


# Closure periods are anchored to the run date rather than written as literals. SCRUM-62
# refuses a period whose end has already passed, so a fixed date turns this whole file red
# the morning it goes by: these were written as 1 Oct 2026 and failed on 2 Oct 2026.
_PLUS_8 = timezone(timedelta(hours=8))
_ANCHOR = (datetime.now(UTC) + timedelta(days=30)).replace(
    hour=9, minute=0, second=0, microsecond=0
)


def _utc(hours: int = 0, days: int = 0) -> str:
    """An instant relative to the anchor, in the `...Z` form the API echoes back."""
    return (_ANCHOR + timedelta(days=days, hours=hours)).isoformat().replace("+00:00", "Z")


def _sgt(hours: int = 0) -> str:
    """The same instant as `_utc(hours)`, written with a +08:00 offset: timezone-aware but
    not UTC, which is what the non-UTC refusal needs."""
    return (_ANCHOR + timedelta(hours=hours)).astimezone(_PLUS_8).isoformat()


def body(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "starts_at": _utc(0),
        "ends_at": _utc(2),
        "reason": "Air-conditioning maintenance",
    }
    values.update(overrides)
    return values


@pytest.mark.story("SCRUM-62")
async def test_venue_staff_create_and_list_an_unavailability(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    async with make_client(make_user("venue_staff")) as client:
        created = await client.post(f"/api/venues/{venue.id}/unavailabilities", json=body())
        listed = await client.get(f"/api/venues/{venue.id}/unavailabilities")

    assert created.status_code == 201
    assert created.json()["reason"] == "Air-conditioning maintenance"
    assert created.json()["starts_at"] == _utc(0)
    assert [record["id"] for record in listed.json()] == [created.json()["id"]]
    assert db.get(VenueUnavailability, uuid.UUID(created.json()["id"])) is not None


@pytest.mark.story("SCRUM-62")
async def test_venue_staff_edit_a_record_without_creating_another(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    async with make_client(make_user("venue_staff")) as client:
        created = await client.post(f"/api/venues/{venue.id}/unavailabilities", json=body())
        updated = await client.put(
            f"/api/venues/{venue.id}/unavailabilities/{created.json()['id']}",
            json=body(ends_at=_utc(3), reason="Extended maintenance"),
        )

    assert updated.status_code == 200
    assert updated.json()["reason"] == "Extended maintenance"
    assert updated.json()["ends_at"] == _utc(3)
    assert len(db.query(VenueUnavailability).all()) == 1


@pytest.mark.story("SCRUM-62")
async def test_venue_staff_delete_a_record(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    url = f"/api/venues/{venue.id}/unavailabilities"

    async with make_client(make_user("venue_staff")) as client:
        first = await client.post(url, json=body())
        second = await client.post(
            url,
            json=body(
                starts_at=_utc(0, days=1),
                ends_at=_utc(2, days=1),
            ),
        )
        deleted = await client.delete(f"{url}/{first.json()['id']}")
        listed = await client.get(url)

    assert first.status_code == 201
    assert second.status_code == 201
    assert deleted.status_code == 204
    assert listed.status_code == 200
    assert [record["id"] for record in listed.json()] == [second.json()["id"]]


@pytest.mark.story("SCRUM-62")
@pytest.mark.parametrize("role", ["coordinator", "organiser", "attendee"])
async def test_non_venue_staff_cannot_mutate_unavailability(
    db: Session, make_user: MakeUser, make_client: MakeClient, role: str
) -> None:
    venue = make_venue(db)
    async with make_client(make_user("venue_staff")) as staff:
        created = await staff.post(f"/api/venues/{venue.id}/unavailabilities", json=body())
    url = f"/api/venues/{venue.id}/unavailabilities/{created.json()['id']}"

    async with make_client(make_user(role)) as client:
        create_attempt = await client.post(f"/api/venues/{venue.id}/unavailabilities", json=body())
        assert (await client.put(url, json=body(reason="Changed"))).status_code == 403
        assert (await client.delete(url)).status_code == 403
    assert create_attempt.status_code == 403


@pytest.mark.story("SCRUM-62")
async def test_create_rejects_an_inactive_venue_and_invalid_period(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    inactive = make_venue(db, is_active=False)
    active = make_venue(db)
    async with make_client(make_user("venue_staff")) as client:
        inactive_response = await client.post(
            f"/api/venues/{inactive.id}/unavailabilities", json=body()
        )
        invalid_response = await client.post(
            f"/api/venues/{active.id}/unavailabilities",
            json=body(ends_at=_utc(0)),
        )

    assert inactive_response.status_code == 409
    assert invalid_response.status_code == 422
    assert invalid_response.json()["detail"] == [
        {"field": "ends_at", "reason": "must be after the start time"}
    ]


@pytest.mark.story("SCRUM-62")
async def test_create_rejects_a_closure_that_has_already_ended(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    ended_at = datetime.now(UTC) - timedelta(minutes=1)
    async with make_client(make_user("venue_staff")) as client:
        response = await client.post(
            f"/api/venues/{venue.id}/unavailabilities",
            json=body(
                starts_at=(ended_at - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
                ends_at=ended_at.isoformat().replace("+00:00", "Z"),
            ),
        )

    assert response.status_code == 422
    assert response.json()["detail"] == [{"field": "ends_at", "reason": "must be in the future"}]


@pytest.mark.story("SCRUM-62")
async def test_create_rejects_aware_non_utc_datetimes(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    async with make_client(make_user("venue_staff")) as client:
        response = await client.post(
            f"/api/venues/{venue.id}/unavailabilities",
            json=body(
                starts_at=_sgt(0),
                ends_at=_sgt(2),
            ),
        )

    assert response.status_code == 422
    assert response.json()["detail"] == [
        {"field": "starts_at", "reason": "must be given in UTC"},
        {"field": "ends_at", "reason": "must be given in UTC"},
    ]


@pytest.mark.story("SCRUM-62")
async def test_update_cannot_reach_a_closure_at_another_venue(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    first_venue = make_venue(db)
    second_venue = make_venue(db)
    first_url = f"/api/venues/{first_venue.id}/unavailabilities"
    async with make_client(make_user("venue_staff")) as client:
        created = await client.post(first_url, json=body())
        response = await client.put(
            f"/api/venues/{second_venue.id}/unavailabilities/{created.json()['id']}",
            json=body(reason="Attempted cross-venue update"),
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Venue unavailability not found"
    assert db.get(VenueUnavailability, uuid.UUID(created.json()["id"])) is not None


@pytest.mark.story("SCRUM-62")
async def test_delete_cannot_reach_a_closure_at_another_venue(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    first_venue = make_venue(db)
    second_venue = make_venue(db)
    first_url = f"/api/venues/{first_venue.id}/unavailabilities"
    async with make_client(make_user("venue_staff")) as client:
        created = await client.post(first_url, json=body())
        response = await client.delete(
            f"/api/venues/{second_venue.id}/unavailabilities/{created.json()['id']}"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Venue unavailability not found"
    assert db.get(VenueUnavailability, uuid.UUID(created.json()["id"])) is not None


@pytest.mark.story("SCRUM-62")
async def test_unknown_venue_is_not_available_for_listing_or_creation(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    url = f"/api/venues/{uuid.uuid4()}/unavailabilities"
    async with make_client(make_user("venue_staff")) as client:
        listed = await client.get(url)
        created = await client.post(url, json=body())

    assert listed.status_code == 404
    assert created.status_code == 404
    assert listed.json()["detail"] == "Venue not found"
    assert created.json()["detail"] == "Venue not found"


@pytest.mark.story("SCRUM-62")
async def test_update_rejects_an_unknown_closure(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    async with make_client(make_user("venue_staff")) as client:
        response = await client.put(
            f"/api/venues/{venue.id}/unavailabilities/{uuid.uuid4()}", json=body()
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Venue unavailability not found"


@pytest.mark.story("SCRUM-62")
async def test_delete_rejects_an_unknown_closure(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    async with make_client(make_user("venue_staff")) as client:
        response = await client.delete(f"/api/venues/{venue.id}/unavailabilities/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Venue unavailability not found"


# ----------------------------------- a closure cannot land on a confirmed booking


def confirm_booking(
    db: Session, venue: Venue, make_user: MakeUser, hours_from_anchor: int, length: int = 2
) -> VenueBooking:
    """A confirmed booking at this venue, as the thing a closure must not sit on top of."""
    coordinator = make_user("coordinator")
    start = _ANCHOR + timedelta(hours=hours_from_anchor)
    end = start + timedelta(hours=length)
    event = approved_event(db, coordinator, coordinator, start_at=start, end_at=end)
    effective_start, effective_end = effective_for(venue, start, end)
    booking = VenueBooking(
        venue_id=venue.id,
        event_request_id=event.id,
        requested_by_id=coordinator.id,
        session_label="Opening keynote",
        start_at=start,
        end_at=end,
        effective_start_at=effective_start,
        effective_end_at=effective_end,
        status=BookingStatus.CONFIRMED,
    )
    db.add(booking)
    db.flush()
    return booking


@pytest.mark.story("SCRUM-62")
async def test_a_closure_over_a_confirmed_booking_is_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """Reported from end-to-end testing: the venue was both promised and shut.

    Nothing downstream could resolve it. SCRUM-73 refuses an *approval* that clashes with
    a closure, but this booking was already approved, so the clash had no owner.
    """
    venue = make_venue(db)
    booking = confirm_booking(db, venue, make_user, hours_from_anchor=0)

    async with make_client(make_user("venue_staff")) as client:
        response = await client.post(f"/api/venues/{venue.id}/unavailabilities", json=body())

    assert response.status_code == 409
    detail = response.json()["detail"]
    # Readable by the person being refused, not just by whoever reads the logs.
    assert "already committed to a confirmed booking" in detail
    assert str(booking.id) in detail
    assert db.query(VenueUnavailability).count() == 0


@pytest.mark.story("SCRUM-62")
async def test_a_closure_that_misses_every_booking_is_allowed(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # The booking runs 10 to 12 hours after the anchor; the closure is the first 2 hours.
    venue = make_venue(db)
    confirm_booking(db, venue, make_user, hours_from_anchor=10)

    async with make_client(make_user("venue_staff")) as client:
        response = await client.post(f"/api/venues/{venue.id}/unavailabilities", json=body())

    assert response.status_code == 201, response.text


@pytest.mark.story("SCRUM-62")
async def test_a_closure_touching_a_booking_end_to_end_is_allowed(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # Half-open, as everywhere else: a closure starting exactly when a booking ends is
    # not an overlap. The booking occupies [anchor, anchor+2); the closure starts at +2.
    venue = make_venue(db)
    confirm_booking(db, venue, make_user, hours_from_anchor=0)

    async with make_client(make_user("venue_staff")) as client:
        response = await client.post(
            f"/api/venues/{venue.id}/unavailabilities",
            json=body(starts_at=_utc(2), ends_at=_utc(4)),
        )

    assert response.status_code == 201, response.text


@pytest.mark.story("SCRUM-62")
async def test_a_closure_reaching_into_setup_time_is_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # SCRUM-82 AC5 from the other side: the booking is widened by the venue's buffers and
    # the closure is not, so a closure that only touches the preparation time still
    # clashes. Without this the venue would be shut while an event was being set up.
    venue = make_venue(db)
    venue.setup_minutes = 60
    db.flush()
    confirm_booking(db, venue, make_user, hours_from_anchor=3)

    async with make_client(make_user("venue_staff")) as client:
        # The event runs from +3h, so with an hour of setup the venue is occupied from
        # +2h. A closure of +1h to +3h never touches the event itself and still clashes.
        response = await client.post(
            f"/api/venues/{venue.id}/unavailabilities",
            json=body(starts_at=_utc(1), ends_at=_utc(3)),
        )

    assert response.status_code == 409, response.text


@pytest.mark.story("SCRUM-62")
async def test_a_pending_request_does_not_stop_a_closure(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # A request nobody has approved is not a commitment, and letting one block
    # maintenance would hand any coordinator a veto over the venue.
    venue = make_venue(db)
    booking = confirm_booking(db, venue, make_user, hours_from_anchor=0)
    booking.status = BookingStatus.PENDING
    db.flush()

    async with make_client(make_user("venue_staff")) as client:
        response = await client.post(f"/api/venues/{venue.id}/unavailabilities", json=body())

    assert response.status_code == 201, response.text


@pytest.mark.story("SCRUM-62")
async def test_a_closure_cannot_be_edited_onto_a_confirmed_booking(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """Otherwise `update` is the way round `create`'s check.

    Record a closure somewhere clear, then move it on top of a confirmed booking and the
    venue ends up both promised and shut by the back door.
    """
    venue = make_venue(db)
    booking = confirm_booking(db, venue, make_user, hours_from_anchor=10)

    async with make_client(make_user("venue_staff")) as client:
        created = await client.post(f"/api/venues/{venue.id}/unavailabilities", json=body())
        assert created.status_code == 201, created.text
        edited = await client.put(
            f"/api/venues/{venue.id}/unavailabilities/{created.json()['id']}",
            json=body(starts_at=_utc(10), ends_at=_utc(12)),
        )

    assert edited.status_code == 409
    assert str(booking.id) in edited.json()["detail"]
    # Refused means unchanged, not partly applied.
    db.expire_all()
    stored = db.query(VenueUnavailability).one()
    assert stored.starts_at == _ANCHOR


@pytest.mark.story("SCRUM-62")
async def test_a_closure_clear_of_every_booking_can_still_be_edited(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # The check must not be so eager that an ordinary edit stops working. The booking is
    # ten hours away from both the old period and the new one.
    venue = make_venue(db)
    confirm_booking(db, venue, make_user, hours_from_anchor=10)

    async with make_client(make_user("venue_staff")) as client:
        created = await client.post(f"/api/venues/{venue.id}/unavailabilities", json=body())
        edited = await client.put(
            f"/api/venues/{venue.id}/unavailabilities/{created.json()['id']}",
            json=body(ends_at=_utc(3), reason="Rescheduled maintenance"),
        )

    assert edited.status_code == 200, edited.text
    assert edited.json()["reason"] == "Rescheduled maintenance"
