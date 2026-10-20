"""SCRUM-81: a venue closure over live arrangements notifies their Coordinators."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from domain.notifications import NotificationType
from domain.venue_booking import BookingStatus
from models.event_request import EventRequest
from models.notification import Notification
from models.user import User
from models.venue_closure_impact import VenueClosureImpact
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_venue_unavailabilities import (
    _ANCHOR,
    _utc,
    body,
    confirm_booking,
    make_venue,
)


def _closure_notes(db: Session) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification).where(Notification.type == NotificationType.VENUE_CLOSURE_IMPACT)
        )
    )


@pytest.mark.story("SCRUM-81")
async def test_each_affected_arrangement_notifies_its_coordinator_once(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC2, AC4: a confirmed booking and a live hold are both affected and notified."""
    venue = make_venue(db)
    booking = confirm_booking(db, venue, make_user, hours_from_anchor=0)
    hold = confirm_booking(db, venue, make_user, hours_from_anchor=3)
    holder = make_user("venue_staff")
    hold.status = BookingStatus.TENTATIVE
    hold.expires_at = _ANCHOR + timedelta(days=1)
    hold.held_by_id = holder.id
    hold.held_at = _ANCHOR - timedelta(days=1)
    db.flush()

    async with make_client(make_user("venue_staff")) as client:
        response = await client.post(
            f"/api/venues/{venue.id}/unavailabilities",
            json=body(starts_at=_utc(0), ends_at=_utc(5)),
        )

    assert response.status_code == 201, response.text
    affected = response.json()["affected"]
    assert [a["booking_id"] for a in affected] == [str(booking.id), str(hold.id)]
    assert affected[0]["session_label"] == "Opening keynote"
    assert affected[0]["event_name"] is not None
    notes = _closure_notes(db)
    assert sorted(n.event_request_id for n in notes) == sorted(
        [booking.event_request_id, hold.event_request_id]
    )


@pytest.mark.story("SCRUM-81")
async def test_a_pending_request_or_a_clear_closure_notifies_nobody(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    pending = confirm_booking(db, venue, make_user, hours_from_anchor=0)
    pending.status = BookingStatus.PENDING
    db.flush()

    async with make_client(make_user("venue_staff")) as client:
        response = await client.post(f"/api/venues/{venue.id}/unavailabilities", json=body())

    assert response.json()["affected"] == []
    assert _closure_notes(db) == []
    assert db.query(VenueClosureImpact).count() == 0


@pytest.mark.story("SCRUM-81")
async def test_re_saving_the_same_period_does_not_notify_twice_but_moving_it_does(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC6, AC8: retries are harmless, a new period is news."""
    venue = make_venue(db)
    confirm_booking(db, venue, make_user, hours_from_anchor=0)

    async with make_client(make_user("venue_staff")) as client:
        created = await client.post(f"/api/venues/{venue.id}/unavailabilities", json=body())
        url = f"/api/venues/{venue.id}/unavailabilities/{created.json()['id']}"
        await client.put(url, json=body())
        assert len(_closure_notes(db)) == 1
        await client.put(url, json=body(starts_at=_utc(1), ends_at=_utc(3)))

    assert len(_closure_notes(db)) == 2


@pytest.mark.story("SCRUM-81")
async def test_the_event_and_booking_are_left_as_they_were(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC3: nothing is cancelled, the closure only reports."""
    venue = make_venue(db)
    booking = confirm_booking(db, venue, make_user, hours_from_anchor=0)
    event = db.get(EventRequest, booking.event_request_id)
    assert event is not None
    before = event.status

    async with make_client(make_user("venue_staff")) as client:
        await client.post(f"/api/venues/{venue.id}/unavailabilities", json=body())

    db.refresh(booking)
    db.refresh(event)
    assert booking.status == BookingStatus.CONFIRMED
    assert booking.start_at == _ANCHOR
    assert event.status == before == EventStatus.APPROVED


@pytest.mark.story("SCRUM-81")
async def test_the_coordinator_sees_the_closure_on_their_booking(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC2, AC3: the existing booking list shows the arrangement needs action."""
    venue = make_venue(db)
    booking = confirm_booking(db, venue, make_user, hours_from_anchor=0)
    async with make_client(make_user("venue_staff")) as client:
        await client.post(f"/api/venues/{venue.id}/unavailabilities", json=body())

    coordinator_id = _closure_notes(db)[0].recipient_id
    coordinator = db.get(User, coordinator_id)
    assert coordinator is not None
    async with make_client(coordinator) as client:
        listed = await client.get(f"/api/event-requests/{booking.event_request_id}/venue-bookings")
    async with make_client(make_user("coordinator")) as client:
        refused = await client.get(f"/api/event-requests/{booking.event_request_id}/venue-bookings")

    assert listed.status_code == 200
    [row] = listed.json()
    assert row["conflict"] is not None
    assert row["conflict"]["kind"] == "unavailability"
    assert refused.status_code == 403


@pytest.mark.story("SCRUM-81")
async def test_an_event_with_no_coordinator_is_still_recorded(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC4: zero recipients does not break the closure."""
    venue = make_venue(db)
    booking = confirm_booking(db, venue, make_user, hours_from_anchor=0)
    event = db.get(EventRequest, booking.event_request_id)
    assert event is not None
    event.coordinator_id = None
    db.flush()

    async with make_client(make_user("venue_staff")) as client:
        response = await client.post(f"/api/venues/{venue.id}/unavailabilities", json=body())

    assert response.status_code == 201
    assert len(response.json()["affected"]) == 1
    assert _closure_notes(db) == []


@pytest.mark.story("SCRUM-81")
async def test_the_impact_snapshot_outlives_the_closure(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC7: who saved what, and which arrangements it hit, is kept for history."""
    venue = make_venue(db)
    booking = confirm_booking(db, venue, make_user, hours_from_anchor=0)
    staff = make_user("venue_staff")

    async with make_client(staff) as client:
        created = await client.post(f"/api/venues/{venue.id}/unavailabilities", json=body())
        await client.delete(f"/api/venues/{venue.id}/unavailabilities/{created.json()['id']}")

    [impact] = db.query(VenueClosureImpact).all()
    assert impact.unavailability_id == uuid.UUID(created.json()["id"])
    assert impact.recorded_by_id == staff.id
    assert impact.affected_booking_ids == [booking.id]
    assert impact.starts_at == _ANCHOR
    assert impact.ends_at == _ANCHOR + timedelta(hours=2)
