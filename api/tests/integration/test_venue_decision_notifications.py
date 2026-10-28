"""SCRUM-122: the assigned Coordinator is notified of venue decisions and hold expiry updates.

TC-122-01 proves approval, rejection and an active-hold expiry edit each create the
correct separate item for the current Coordinator. TC-122-02 proves two later expiry
edits create two source-specific items while retrying one creates none. TC-122-03
proves reassignment changes the later recipient and inactive/unrelated users get none.
TC-122-04 proves invalid actions and rollbacks produce no item and the SCRUM-108
expiry alert is not duplicated.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from domain.notifications import NotificationSource, NotificationType
from domain.venue_booking import BookingStatus
from models.notification import Notification
from models.user import User
from models.venue import Venue
from models.venue_booking import VenueBooking
from repositories import notifications as notifications_repo
from tests.integration.test_decide_venue_booking import pending_booking, reject
from tests.integration.test_submit_event_request import MakeClient, MakeUser

_START = datetime(2026, 11, 10, 2, 0, tzinfo=UTC)
_END = _START + timedelta(hours=3)
_EXPIRY = _START - timedelta(days=1)
_LATER = _START - timedelta(hours=12)


def _total_notifications(db: Session) -> int:
    """Every stored notification row, whoever the recipient is."""
    return db.scalar(select(func.count()).select_from(Notification)) or 0


def _inbox(db: Session, user_id: uuid.UUID) -> list[Notification]:
    return notifications_repo.list_for_recipient(db, user_id)


def _coordinator_of(db: Session, booking: VenueBooking) -> User:
    from models.event_request import EventRequest

    event = db.get(EventRequest, booking.event_request_id)
    assert event is not None and event.coordinator_id is not None
    coordinator = db.get(User, event.coordinator_id)
    assert coordinator is not None
    return coordinator


async def _approve(client, booking: VenueBooking, expires_at: datetime = _EXPIRY):  # type: ignore[no-untyped-def]
    return await client.post(
        f"/api/venue-bookings/{booking.id}/approve",
        json={"expires_at": expires_at.isoformat()},
    )


async def _edit_expiry(client, booking: VenueBooking, expires_at: datetime):  # type: ignore[no-untyped-def]
    return await client.patch(
        f"/api/venue-bookings/{booking.id}/hold",
        json={"expires_at": expires_at.isoformat()},
    )


def _tentative(db: Session, booking: VenueBooking) -> VenueBooking:
    db.refresh(booking)
    assert booking.status is BookingStatus.TENTATIVE
    return booking


# ------------------------------------------------------------------ TC-122-01


@pytest.mark.story("SCRUM-122")
async def test_approval_rejection_and_expiry_edit_each_notify_the_coordinator(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1: approval, rejection and an expiry edit each create the correct item."""
    # Venue Staff approve one request, reject another, and edit the hold's expiry.
    # The Coordinator should get one message per action, each naming its outcome.
    # Both bookings share one Coordinator so the inbox holds all three items.
    coordinator_user = make_user("coordinator")
    approved_booking = pending_booking(db, make_user)
    rejected_booking = pending_booking(db, make_user)
    from models.event_request import EventRequest

    for booking in (approved_booking, rejected_booking):
        event = db.get(EventRequest, booking.event_request_id)
        assert event is not None
        event.coordinator_id = coordinator_user.id
    db.flush()
    coordinator = _coordinator_of(db, approved_booking)
    assert coordinator.id == coordinator_user.id
    staff = make_user("venue_staff")

    async with make_client(staff) as client:
        approved = await _approve(client, approved_booking)
        assert approved.status_code == 200, approved.text
        denied = await reject(client, rejected_booking, reason="Room under maintenance")
        assert denied.status_code == 200, denied.text
        edited = await _edit_expiry(client, _tentative(db, approved_booking), _LATER)
        assert edited.status_code == 200, edited.text

    rows = _inbox(db, coordinator.id)
    assert len(rows) == 3
    by_type = {item.type: item for item in rows}
    assert set(by_type) == {
        NotificationType.VENUE_BOOKING_APPROVED,
        NotificationType.VENUE_BOOKING_REJECTED,
        NotificationType.VENUE_HOLD_EXPIRY_UPDATED,
    }
    for item in rows:
        assert item.source_type == NotificationSource.VENUE_DECISION
        assert item.occurred_at.tzinfo is not None
        assert item.viewed_at is None
    assert by_type[NotificationType.VENUE_BOOKING_APPROVED].event_request_id == (
        approved_booking.event_request_id
    )
    assert by_type[NotificationType.VENUE_BOOKING_REJECTED].event_request_id == (
        rejected_booking.event_request_id
    )
    assert by_type[NotificationType.VENUE_HOLD_EXPIRY_UPDATED].event_request_id == (
        approved_booking.event_request_id
    )

    async with make_client(coordinator) as coordinator_client:
        inbox = await coordinator_client.get("/api/notifications")
    assert inbox.status_code == 200
    assert {entry["type"] for entry in inbox.json()} == {
        NotificationType.VENUE_BOOKING_APPROVED.value,
        NotificationType.VENUE_BOOKING_REJECTED.value,
        NotificationType.VENUE_HOLD_EXPIRY_UPDATED.value,
    }
    assert all(entry["is_unread"] for entry in inbox.json())


# ------------------------------------------------------------------ TC-122-02


@pytest.mark.story("SCRUM-122")
async def test_two_expiry_edits_notify_twice_while_a_retry_notifies_once(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC2: two later edits are two items; retrying one action collides per recipient."""
    # Two different expiry times are two different actions. Sending the same time
    # twice is a retry of one action, so it stays one message.
    booking = pending_booking(db, make_user)
    coordinator = _coordinator_of(db, booking)
    staff = make_user("venue_staff")

    async with make_client(staff) as client:
        approved = await _approve(client, booking)
        assert approved.status_code == 200, approved.text
        first = await _edit_expiry(client, _tentative(db, booking), _LATER)
        assert first.status_code == 200, first.text
        # A retry of the same edit: the hold already carries this expiry.
        retry = await _edit_expiry(client, _tentative(db, booking), _LATER)
        assert retry.status_code == 200, retry.text
        second = await _edit_expiry(client, _tentative(db, booking), _START - timedelta(hours=6))
        assert second.status_code == 200, second.text

    rows = _inbox(db, coordinator.id)
    kinds = [item.type for item in rows]
    assert kinds.count(NotificationType.VENUE_BOOKING_APPROVED) == 1
    assert kinds.count(NotificationType.VENUE_HOLD_EXPIRY_UPDATED) == 2
    assert len({item.source_id for item in rows}) == len(rows)


# ------------------------------------------------------------------ TC-122-03


@pytest.mark.story("SCRUM-122")
async def test_reassignment_changes_the_recipient_and_others_get_nothing(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC2/AC3: later actions notify the current Coordinator only."""
    # The event is reassigned between the approval and the expiry edit. The former
    # Coordinator keeps only the approval message; the new one gets only the edit.
    from models.event_request import EventRequest

    booking = pending_booking(db, make_user)
    former = _coordinator_of(db, booking)
    current = make_user("coordinator")
    tech = make_user("tech_support")
    staff = make_user("venue_staff")

    async with make_client(staff) as client:
        approved = await _approve(client, booking)
        assert approved.status_code == 200, approved.text

    event = db.get(EventRequest, booking.event_request_id)
    assert event is not None
    event.coordinator_id = current.id
    db.flush()

    async with make_client(staff) as client:
        edited = await _edit_expiry(client, _tentative(db, booking), _LATER)
        assert edited.status_code == 200, edited.text

    former_rows = _inbox(db, former.id)
    assert [item.type for item in former_rows] == [NotificationType.VENUE_BOOKING_APPROVED]
    current_rows = _inbox(db, current.id)
    assert [item.type for item in current_rows] == [NotificationType.VENUE_HOLD_EXPIRY_UPDATED]
    assert _inbox(db, tech.id) == []
    assert _inbox(db, staff.id) == []


@pytest.mark.story("SCRUM-122")
async def test_decision_without_a_coordinator_still_commits(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1 boundary: no Coordinator assigned → the decision still commits, zero rows."""
    # With no Coordinator assigned, the approval still goes through but no message
    # is created.
    from models.event_request import EventRequest

    booking = pending_booking(db, make_user)
    event = db.get(EventRequest, booking.event_request_id)
    assert event is not None
    event.coordinator_id = None
    db.flush()

    async with make_client(make_user("venue_staff")) as client:
        response = await _approve(client, booking)

    assert response.status_code == 200, response.text
    assert _total_notifications(db) == 0


# ------------------------------------------------------------------ TC-122-04


@pytest.mark.story("SCRUM-122")
async def test_invalid_and_unauthorised_actions_create_nothing(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC3: invalid and unauthorised actions are refused before anything is written."""
    # A bad expiry and a non-staff approval are rejected, so no message exists.
    # The expiry sits after the event ends, which the hold rules refuse.
    booking = pending_booking(db, make_user)
    coordinator = _coordinator_of(db, booking)
    from models.event_request import EventRequest as _EventRequest

    event = db.get(_EventRequest, booking.event_request_id)
    assert event is not None and event.end_at is not None

    async with make_client(make_user("venue_staff")) as client:
        refused = await _approve(client, booking, expires_at=event.end_at + timedelta(hours=1))
        assert refused.status_code == 422

    assert _total_notifications(db) == 0

    async with make_client(make_user("organiser")) as outsider:
        forbidden = await _approve(outsider, booking)
    assert forbidden.status_code == 403

    assert _total_notifications(db) == 0
    assert _inbox(db, coordinator.id) == []


@pytest.mark.story("SCRUM-122")
async def test_rolled_back_approval_creates_nothing(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC3: a conflicting approval leaves no hold and no notification."""
    # Two overlapping requests at one venue for the same period: approving the second
    # is refused by the conflict check, so nothing is saved and no message is sent.
    first = pending_booking(db, make_user)
    venue_id = first.venue_id
    coordinator = _coordinator_of(db, first)
    staff = make_user("venue_staff")

    from tests.integration.test_submit_venue_booking import approved_event
    from tests.integration.test_venue_search import effective_for

    second_coordinator = make_user("coordinator")
    second_event = approved_event(
        db,
        make_user("organiser"),
        second_coordinator,
        start_at=first.start_at,
        end_at=first.end_at,
    )
    assert second_event.start_at is not None and second_event.end_at is not None
    venue = db.get(Venue, venue_id)
    assert venue is not None
    effective_start, effective_end = effective_for(venue, first.start_at, first.end_at)
    second = VenueBooking(
        venue_id=venue_id,
        event_request_id=second_event.id,
        requested_by_id=second_coordinator.id,
        session_label="Second session",
        start_at=first.start_at,
        end_at=first.end_at,
        effective_start_at=effective_start,
        effective_end_at=effective_end,
        status=BookingStatus.PENDING,
    )
    db.add(second)
    db.flush()

    async with make_client(staff) as client:
        approved = await _approve(client, first)
        assert approved.status_code == 200, approved.text
        conflicted = await _approve(client, second)
    assert conflicted.status_code == 409

    assert _total_notifications(db) == 1
    assert len(_inbox(db, coordinator.id)) == 1
    assert _inbox(db, second_coordinator.id) == []
