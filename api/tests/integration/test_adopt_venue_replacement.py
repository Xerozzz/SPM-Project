"""SCRUM-133: the assigned Coordinator adopts an approved replacement venue request."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from domain.venue_booking import BookingStatus
from models.event_request import EventRequest
from models.user import User
from models.venue_booking import VenueBooking
from repositories import venue_availability as booking_repo
from services import venue_replacements as service
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_venue_replacement import _affected, _replacement, _request
from tests.integration.test_venue_search import effective_for
from tests.integration.test_venue_unavailabilities import make_venue


async def _with_replacement(
    db: Session, make_user: MakeUser, make_client: MakeClient, approve: bool = True
) -> tuple[VenueBooking, User, str]:
    """An affected confirmed booking, its Coordinator and a replacement request id.

    With `approve`, Venue Staff approve the replacement through SCRUM-110 (a hold).
    """
    original, coordinator = await _affected(db, make_user, make_client)
    async with make_client(coordinator) as client:
        created = await _request(client, original, _replacement(original, make_venue(db).id))
    assert created.status_code == 201, created.text
    replacement_id = created.json()["id"]
    if approve:
        async with make_client(make_user("venue_staff")) as client:
            held = await client.post(
                f"/api/venue-bookings/{replacement_id}/approve",
                json={"expires_at": (datetime.now(UTC) + timedelta(days=7)).isoformat()},
            )
        assert held.status_code == 200, held.text
    return original, coordinator, replacement_id


def _url(original: VenueBooking, booking_id: object) -> str:
    return f"/api/event-requests/{original.event_request_id}/venue-bookings/{booking_id}/adopt"


def _fresh(db: Session, booking_id: object) -> VenueBooking:
    db.expire_all()
    row = db.get(VenueBooking, uuid.UUID(str(booking_id)))
    assert row is not None
    return row


# --------------------------------------------------------------------------- AC1, AC3


@pytest.mark.story("SCRUM-133")
async def test_adopting_cancels_the_original_and_keeps_the_link(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    original, coordinator, replacement_id = await _with_replacement(db, make_user, make_client)

    async with make_client(coordinator) as client:
        response = await client.post(_url(original, replacement_id))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "tentative"
    assert body["replaces_booking_id"] == str(original.id)
    assert body["adopted_by_id"] == str(coordinator.id)
    assert body["adopted_at"] is not None
    old = _fresh(db, original.id)
    assert old.status == BookingStatus.CANCELLED
    assert old.cancelled_by_id == coordinator.id
    assert old.cancellation_reason == service.ADOPTION_REASON


@pytest.mark.story("SCRUM-133")
async def test_other_arrangements_and_the_event_are_left_alone(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1 and AC2: no other booking is cancelled and the event is not reconfirmed."""
    original, coordinator, replacement_id = await _with_replacement(db, make_user, make_client)
    venue = make_venue(db)
    start, end = original.start_at, original.end_at
    held_from, held_to = effective_for(venue, start, end)
    other = VenueBooking(
        venue_id=venue.id,
        event_request_id=original.event_request_id,
        requested_by_id=coordinator.id,
        session_label="Breakout",
        start_at=start,
        end_at=end,
        effective_start_at=held_from,
        effective_end_at=held_to,
        status=BookingStatus.CONFIRMED,
    )
    db.add(other)
    db.flush()

    async with make_client(coordinator) as client:
        response = await client.post(_url(original, replacement_id))

    assert response.status_code == 200
    assert _fresh(db, other.id).status == BookingStatus.CONFIRMED
    event = db.get(EventRequest, original.event_request_id)
    assert event is not None and event.status is EventStatus.APPROVED


# --------------------------------------------------------------------------- AC2


@pytest.mark.story("SCRUM-133")
async def test_a_replacement_not_yet_approved_cannot_be_adopted(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    original, coordinator, replacement_id = await _with_replacement(
        db, make_user, make_client, approve=False
    )

    async with make_client(coordinator) as client:
        response = await client.post(_url(original, replacement_id))

    assert response.status_code == 409
    assert response.json()["detail"] == "Venue Staff have not approved this replacement"
    assert _fresh(db, original.id).status == BookingStatus.CONFIRMED
    assert _fresh(db, replacement_id).adopted_at is None


@pytest.mark.story("SCRUM-133")
async def test_a_request_that_replaces_nothing_cannot_be_adopted(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    original, coordinator, _ = await _with_replacement(db, make_user, make_client)

    async with make_client(coordinator) as client:
        response = await client.post(_url(original, original.id))

    assert response.status_code == 409
    assert response.json()["detail"] == "This request does not replace another arrangement"


@pytest.mark.story("SCRUM-133")
async def test_a_confirmed_event_is_refused_and_nothing_changes(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    original, coordinator, replacement_id = await _with_replacement(db, make_user, make_client)
    event = db.get(EventRequest, original.event_request_id)
    assert event is not None
    event.status = EventStatus.CONFIRMED
    db.flush()

    async with make_client(coordinator) as client:
        response = await client.post(_url(original, replacement_id))

    assert response.status_code == 409
    assert _fresh(db, original.id).status == BookingStatus.CONFIRMED
    assert _fresh(db, replacement_id).adopted_at is None


# --------------------------------------------------------------------------- AC3


@pytest.mark.story("SCRUM-133")
async def test_only_the_assigned_coordinator_can_adopt(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    original, _, replacement_id = await _with_replacement(db, make_user, make_client)

    for role in ("organiser", "coordinator", "venue_staff", "coordinator_lead"):
        async with make_client(make_user(role)) as client:
            response = await client.post(_url(original, replacement_id))
        assert response.status_code == 403, role

    assert _fresh(db, original.id).status == BookingStatus.CONFIRMED


@pytest.mark.story("SCRUM-133")
async def test_an_unknown_request_is_not_found(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    original, coordinator, _ = await _with_replacement(db, make_user, make_client)

    async with make_client(coordinator) as client:
        response = await client.post(_url(original, uuid.uuid4()))

    assert response.status_code == 404


# --------------------------------------------------------------------------- AC4


@pytest.mark.story("SCRUM-133")
async def test_adopting_twice_has_no_extra_effect(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    original, coordinator, replacement_id = await _with_replacement(db, make_user, make_client)

    async with make_client(coordinator) as client:
        first = await client.post(_url(original, replacement_id))
        cancelled_at = _fresh(db, original.id).cancelled_at
        again = await client.post(_url(original, replacement_id))

    assert first.status_code == again.status_code == 200
    assert again.json()["adopted_at"] == first.json()["adopted_at"]
    assert _fresh(db, original.id).cancelled_at == cancelled_at


@pytest.mark.story("SCRUM-133")
async def test_an_original_no_longer_live_is_refused_and_the_link_stays(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """The original was cancelled on its own first, so adopting it now changes nothing."""
    original, coordinator, replacement_id = await _with_replacement(db, make_user, make_client)
    async with make_client(coordinator) as client:
        cancelled = await client.post(
            f"/api/event-requests/{original.event_request_id}/venue-bookings/{original.id}/cancel",
            json={"reason": "No longer needed"},
        )
        response = await client.post(_url(original, replacement_id))

    assert cancelled.status_code == 200, cancelled.text
    assert response.status_code == 409
    assert response.json()["detail"] == "This arrangement has already been cancelled"
    replacement = _fresh(db, replacement_id)
    assert replacement.adopted_at is None
    assert replacement.replaces_booking_id == original.id


@pytest.mark.story("SCRUM-133")
async def test_a_failure_after_the_cancellation_rolls_both_back(
    db: Session, make_user: MakeUser, make_client: MakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    original, coordinator, replacement_id = await _with_replacement(db, make_user, make_client)
    db.commit()

    def broken(*_: object) -> VenueBooking:
        raise RuntimeError("database went away")

    monkeypatch.setattr(booking_repo, "save_booking", broken)
    with pytest.raises(RuntimeError):
        service.adopt(
            db,
            original.event_request_id,
            uuid.UUID(replacement_id),
            coordinator.id,
            datetime.now(UTC),
        )
    db.rollback()
    monkeypatch.undo()

    assert _fresh(db, original.id).status == BookingStatus.CONFIRMED
    replacement = _fresh(db, replacement_id)
    assert replacement.adopted_at is None
    assert replacement.replaces_booking_id == original.id


@pytest.mark.story("SCRUM-133")
async def test_another_events_replacement_is_not_found_here(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """Even one already adopted: its id must not show anything through another event."""
    theirs, their_coordinator, their_replacement = await _with_replacement(
        db, make_user, make_client
    )
    async with make_client(their_coordinator) as client:
        assert (await client.post(_url(theirs, their_replacement))).status_code == 200
    mine, my_coordinator, _ = await _with_replacement(db, make_user, make_client)

    async with make_client(my_coordinator) as client:
        response = await client.post(_url(mine, their_replacement))

    assert response.status_code == 404
