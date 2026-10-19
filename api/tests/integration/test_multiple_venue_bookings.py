"""SCRUM-78: sibling venue requests have independent suitability and lifecycles.

SCRUM-110: Venue Staff approval creates a time-limited Tentative hold, never a
confirmation, so the approve legs below send an expiry and expect Tentative.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from domain.venue_booking import BookingStatus
from models.venue_booking import VenueBooking
from tests.integration.test_booking_conflict import _booking, _closure
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_submit_venue_booking import (
    approved_event,
    bookings,
    seed_equipment,
    submit,
)
from tests.integration.test_venue_availability import check
from tests.integration.test_venue_search import make_venue


def _expiry() -> str:
    """An expiry after now and before any booking start in this file."""
    return (datetime.now(UTC) + timedelta(hours=1)).isoformat()


def snapshot(db: Session, booking: VenueBooking) -> tuple[object, ...]:
    """Reload and compare every stored field, including decision metadata and buffers."""
    db.refresh(booking)
    return (
        booking.id,
        booking.event_request_id,
        booking.venue_id,
        booking.requested_by_id,
        booking.start_at,
        booking.end_at,
        booking.effective_start_at,
        booking.effective_end_at,
        booking.status,
        booking.created_at,
        booking.decided_by_id,
        booking.decided_at,
        booking.decision_reason,
    )


@pytest.mark.story("SCRUM-78")
async def test_each_selected_venue_has_its_own_suitability(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator, expected_attendance=150)
    # SCRUM-43: suitability reads the maintained requirements, so the event needs the
    # row approval would have given it rather than only the organiser's string.
    seed_equipment(db, event)
    first = make_venue(db, maximum_capacity=100, facilities=[], supported_layouts=["classroom"])
    second = make_venue(
        db, name="Hall B", maximum_capacity=200, accessibility_features=["Lift access"]
    )

    async with make_client(coordinator) as client:
        responses = [await submit(client, event, venue.id) for venue in (first, second)]

    assert [response.status_code for response in responses] == [201, 201]
    results = [response.json()["suitability"] for response in responses]
    assert [result["expected_attendance"] for result in results] == [150, 150]
    assert [result["venue_capacity"] for result in results] == [100, 200]
    assert [result["mismatch_codes"] for result in results] == [["CAPACITY_EXCEEDED"], []]
    assert [result["unavailable_facilities"] for result in results] == [["Projector"], []]
    assert [result["venue_accessibility"] for result in results] == [
        ["Step-free access"],
        ["Lift access"],
    ]
    assert [result["venue_layouts"] for result in results] == [
        ["classroom"],
        ["theatre", "classroom"],
    ]
    assert all(
        result["accessibility_need"] == event.accessibility_requirement for result in results
    )
    assert all(result["layout_need"] == event.layout_requirement for result in results)


@pytest.mark.story("SCRUM-78")
@pytest.mark.parametrize("missing", [False, True])
async def test_invalid_additional_venue_keeps_existing_booking(
    db: Session, make_user: MakeUser, make_client: MakeClient, missing: bool
) -> None:
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator)
    first = make_venue(db)
    invalid_id = uuid.uuid4() if missing else make_venue(db, name="Inactive", is_active=False).id

    async with make_client(coordinator) as client:
        assert (await submit(client, event, first.id)).status_code == 201
        original = bookings(db)[0]
        before = snapshot(db, original)
        refused = await submit(client, event, invalid_id)

    assert refused.status_code == 422
    assert refused.json()["detail"] == [
        {
            "field": "venue_id",
            "reason": "does not identify a venue" if missing else "must identify an active venue",
        }
    ]
    assert bookings(db) == [original]
    assert snapshot(db, original) == before


@pytest.mark.story("SCRUM-78")
async def test_unassigned_coordinator_cannot_add_or_read_sibling_bookings(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator)
    first, second = make_venue(db), make_venue(db, name="Hall B")
    async with make_client(coordinator) as client:
        assert (await submit(client, event, first.id)).status_code == 201
    original = bookings(db)[0]
    before = snapshot(db, original)

    async with make_client(make_user("coordinator")) as client:
        refused = await submit(client, event, second.id)
        history = await client.get(f"/api/event-requests/{event.id}/venue-bookings")
        suitability = await client.get(
            f"/api/event-requests/{event.id}/venue-bookings/suitability",
            params={"venue_id": str(second.id)},
        )

    assert refused.status_code == history.status_code == suitability.status_code == 403
    assert bookings(db) == [original]
    assert snapshot(db, original) == before


@pytest.mark.story("SCRUM-78")
@pytest.mark.parametrize("action", ["approve", "reject"])
async def test_deciding_one_booking_keeps_its_sibling_unchanged(
    db: Session, make_user: MakeUser, make_client: MakeClient, action: str
) -> None:
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator)
    async with make_client(coordinator) as client:
        for venue in (make_venue(db), make_venue(db, name="Hall B")):
            assert (await submit(client, event, venue.id)).status_code == 201
    target, sibling = bookings(db)
    before = snapshot(db, sibling)

    async with make_client(make_user("venue_staff")) as client:
        if action == "approve":
            response = await client.post(
                f"/api/venue-bookings/{target.id}/{action}", json={"expires_at": _expiry()}
            )
        else:
            response = await client.post(f"/api/venue-bookings/{target.id}/{action}", json={})

    assert response.status_code == 200
    db.refresh(target)
    assert target.status == (
        BookingStatus.TENTATIVE if action == "approve" else BookingStatus.REJECTED
    )
    assert snapshot(db, sibling) == before
    assert bookings(db) == [target, sibling]
    db.refresh(event)
    assert event.status is EventStatus.APPROVED


@pytest.mark.story("SCRUM-78")
@pytest.mark.parametrize("blocker", ["confirmed", "closure"])
async def test_conflict_on_one_venue_does_not_block_or_mutate_its_sibling(
    db: Session, make_user: MakeUser, make_client: MakeClient, blocker: str
) -> None:
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator)
    first, second = make_venue(db), make_venue(db, name="Hall B")
    async with make_client(coordinator) as client:
        for venue in (first, second):
            assert (await submit(client, event, venue.id)).status_code == 201
    target, sibling = bookings(db)
    target_before, sibling_before = snapshot(db, target), snapshot(db, sibling)
    if blocker == "confirmed":
        _booking(db, coordinator, first, target.start_at, target.end_at)
    else:
        _closure(db, first, target.start_at, target.end_at)

    async with make_client(coordinator) as client:
        busy = await check(client, first.id, target.start_at, target.end_at)
        free = await check(client, second.id, sibling.start_at, sibling.end_at)
    assert busy.status_code == free.status_code == 200
    assert busy.json()["available"] is False
    assert free.json()["available"] is True
    async with make_client(make_user("venue_staff")) as client:
        refused = await client.post(
            f"/api/venue-bookings/{target.id}/approve", json={"expires_at": _expiry()}
        )
        assert refused.status_code == 409
        assert snapshot(db, target) == target_before
        assert snapshot(db, sibling) == sibling_before
        approved = await client.post(
            f"/api/venue-bookings/{sibling.id}/approve", json={"expires_at": _expiry()}
        )

    assert approved.status_code == 200
    assert snapshot(db, target) == target_before
    db.refresh(sibling)
    assert sibling.status is BookingStatus.TENTATIVE

    assert approved.status_code == 200
    assert snapshot(db, target) == target_before
    db.refresh(sibling)
    assert sibling.status is BookingStatus.TENTATIVE


@pytest.mark.story("SCRUM-78")
async def test_pending_same_venue_requests_remain_nonblocking_until_one_is_confirmed(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """SCRUM-110: approval creates a hold, so the second overlapping request is refused
    while the first is Tentative — pending requests stay non-blocking until one holds."""
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator)
    venue = make_venue(db)
    async with make_client(coordinator) as client:
        for _ in range(2):
            assert (await submit(client, event, venue.id)).status_code == 201
        first, second = bookings(db)
        available = await check(client, venue.id, first.start_at, first.end_at)
    assert available.json()["available"] is True
    second_before = snapshot(db, second)
    async with make_client(make_user("venue_staff")) as client:
        assert (
            await client.post(
                f"/api/venue-bookings/{first.id}/approve", json={"expires_at": _expiry()}
            )
        ).status_code == 200
        assert snapshot(db, second) == second_before
        assert (
            await client.post(
                f"/api/venue-bookings/{second.id}/approve", json={"expires_at": _expiry()}
            )
        ).status_code == 409
    assert snapshot(db, second) == second_before
    db.refresh(first)
    assert first.status is BookingStatus.TENTATIVE
