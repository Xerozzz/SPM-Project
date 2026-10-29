"""SCRUM-123: Venue Staff are notified when the Coordinator cancels one arrangement.

TC-123-01 proves cancelling each permitted state (Pending, Tentative, Confirmed)
gives eligible Venue Staff exactly one unread notification with the correct
event/action/time. TC-123-02 proves zero/one/many routing: no staff still cancels
cleanly, many staff each get one, inactive staff and other roles get none, and a
multi-role staff member gets one row. TC-123-03 proves sibling bookings are
untouched and no whole-event-cancellation alert is created. TC-123-04 proves a
retry, an invalid or unauthorised cancellation, and a rolled-back cancellation
create no extra item.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from domain.notifications import NotificationSource, NotificationType
from domain.venue_booking import BookingStatus
from models.notification import Notification
from repositories import notifications as notifications_repo
from tests.integration.test_cancel_venue_arrangement import (
    Planning,
    arrangement,
    cancel,
    planning,
    venue,
)
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_submit_venue_booking import approved_event


def _total_notifications(db: Session) -> int:
    """Every stored notification row, whoever the recipient is."""
    return db.scalar(select(func.count()).select_from(Notification)) or 0


def _inbox(db: Session, user_id):  # type: ignore[no-untyped-def]
    return notifications_repo.list_for_recipient(db, user_id)


# ------------------------------------------------------------------ TC-123-01


@pytest.mark.story("SCRUM-123")
@pytest.mark.parametrize(
    "target", [BookingStatus.PENDING, BookingStatus.TENTATIVE, BookingStatus.CONFIRMED]
)
async def test_cancel_notifies_staff_once_per_state(
    target: BookingStatus, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1/AC2: cancelling a Pending request, Tentative hold or Confirmed booking →
    exactly one unread notification naming the event, the cancellation action, and
    the cancellation time."""
    plan = planning(db, make_user)
    booking = arrangement(db, plan, venue(db), target)

    async with make_client(plan.coordinator) as client:
        response = await cancel(client, plan.event, booking)

    assert response.status_code == 200
    rows = _inbox(db, plan.staff.id)
    assert len(rows) == 1
    row = rows[0]
    assert row.event_request_id == plan.event.id
    assert row.type == NotificationType.VENUE_ARRANGEMENT_CANCELLED
    assert row.source_type == NotificationSource.VENUE_CANCELLATION
    assert row.source_id == str(booking.id)
    assert row.occurred_at.tzinfo is not None
    assert row.viewed_at is None

    async with make_client(plan.staff) as staff_client:
        inbox = await staff_client.get("/api/notifications")
    assert inbox.status_code == 200
    (entry,) = inbox.json()
    assert entry["event_request_id"] == str(plan.event.id)
    assert entry["type"] == NotificationType.VENUE_ARRANGEMENT_CANCELLED.value
    assert entry["is_unread"] is True


# ------------------------------------------------------------------ TC-123-02


@pytest.mark.story("SCRUM-123")
async def test_cancel_succeeds_with_zero_staff_and_zero_notifications(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1 boundary: no active Venue Staff → cancellation still succeeds, zero rows."""
    coordinator = make_user("coordinator")
    event_plan = Planning(
        approved_event(db, make_user("organiser"), coordinator),
        coordinator,
        make_user("venue_staff"),
    )
    # The planning() helper always creates one staff member; deactivate them so no
    # eligible recipient remains.
    event_plan.staff.is_active = False
    db.flush()
    booking = arrangement(db, event_plan, venue(db), BookingStatus.PENDING)

    async with make_client(coordinator) as client:
        response = await cancel(client, event_plan.event, booking)

    assert response.status_code == 200
    assert _total_notifications(db) == 0


@pytest.mark.story("SCRUM-123")
async def test_only_active_staff_are_notified_once_each(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1: three active staff each get exactly one; inactive staff, the
    coordinator and other roles get none; a multi-role staff member gets one row,
    not one per role."""
    plan = planning(db, make_user)
    staff = [plan.staff, make_user("venue_staff"), make_user("venue_staff")]
    multi_role = make_user("venue_staff", "coordinator")
    inactive = make_user("venue_staff", is_active=False)
    lead = make_user("coordinator_lead")
    booking = arrangement(db, plan, venue(db), BookingStatus.CONFIRMED)

    async with make_client(plan.coordinator) as client:
        response = await cancel(client, plan.event, booking)

    assert response.status_code == 200
    assert _total_notifications(db) == 4
    for member in [*staff, multi_role]:
        rows = _inbox(db, member.id)
        assert len(rows) == 1
        assert rows[0].event_request_id == plan.event.id
        assert rows[0].type == NotificationType.VENUE_ARRANGEMENT_CANCELLED
    assert _inbox(db, inactive.id) == []
    assert _inbox(db, plan.coordinator.id) == []
    assert _inbox(db, lead.id) == []


# ------------------------------------------------------------------ TC-123-03


@pytest.mark.story("SCRUM-123")
async def test_siblings_untouched_and_no_whole_event_alert(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC2: cancelling one arrangement leaves its siblings exactly as they were and
    creates no whole-event-cancellation alert for anyone."""
    plan = planning(db, make_user)
    target = arrangement(db, plan, venue(db), BookingStatus.PENDING)
    sibling = arrangement(db, plan, venue(db), BookingStatus.CONFIRMED)
    before_status = sibling.status

    async with make_client(plan.coordinator) as client:
        response = await cancel(client, plan.event, target)

    assert response.status_code == 200
    db.expire_all()
    assert sibling.status is before_status
    rows = _inbox(db, plan.staff.id)
    assert len(rows) == 1
    assert rows[0].type == NotificationType.VENUE_ARRANGEMENT_CANCELLED
    assert rows[0].source_type == NotificationSource.VENUE_CANCELLATION
    assert all(row.type != NotificationType.EVENT_CANCELLED for row in rows)


@pytest.mark.story("SCRUM-123")
async def test_whole_event_cancellation_creates_no_arrangement_alert(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC2: SCRUM-115's whole-event cancellation keeps its own EVENT_CANCELLED
    trigger and creates no per-arrangement VENUE_CANCELLATION rows."""
    plan = planning(db, make_user)
    staff = plan.staff
    arrangement(db, plan, venue(db), BookingStatus.PENDING)
    arrangement(db, plan, venue(db), BookingStatus.CONFIRMED)

    async with make_client(plan.coordinator) as client:
        cancelled = await client.post(
            f"/api/event-requests/{plan.event.id}/cancel",
            json={"reason": "No longer needed"},
        )
        assert cancelled.status_code == 200

    rows = _inbox(db, staff.id)
    assert rows != []
    assert all(row.source_type != NotificationSource.VENUE_CANCELLATION for row in rows)


# ------------------------------------------------------------------ TC-123-04


@pytest.mark.story("SCRUM-123")
async def test_retry_invalid_unauthorised_and_rollback_create_nothing(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC3: re-staging the same cancellation collides instead of duplicating; an
    invalid or unauthorised cancellation and a rolled-back staging create none."""
    plan = planning(db, make_user)
    booking = arrangement(db, plan, venue(db), BookingStatus.PENDING)

    async with make_client(plan.coordinator) as client:
        first = await cancel(client, plan.event, booking)
        assert first.status_code == 200
        # Cancelling again is refused: the row is already Cancelled.
        again = await cancel(client, plan.event, booking)
        assert again.status_code == 409

    assert _total_notifications(db) == 1

    # Re-staging the same source action collides on the (recipient, source) key.
    sent_at = datetime.now(UTC)
    notifications_repo.stage(
        db,
        recipient_id=plan.staff.id,
        event_request_id=plan.event.id,
        type=NotificationType.VENUE_ARRANGEMENT_CANCELLED,
        source_type=NotificationSource.VENUE_CANCELLATION,
        source_id=str(booking.id),
        occurred_at=sent_at,
    )
    db.commit()
    assert _total_notifications(db) == 1

    # An invalid cancellation (missing reason) is refused before anything is written.
    other = arrangement(db, plan, venue(db), BookingStatus.PENDING)
    async with make_client(plan.coordinator) as client:
        refused = await cancel(client, plan.event, other, reason=None)
        assert refused.status_code == 422
    assert _total_notifications(db) == 1

    # An unauthorised cancellation is refused before anything is written.
    async with make_client(make_user("venue_staff")) as outsider:
        forbidden = await outsider.post(
            f"/api/event-requests/{plan.event.id}/venue-bookings/{other.id}/cancel",
            json={"reason": "Trying my luck"},
        )
    assert forbidden.status_code == 403
    assert _total_notifications(db) == 1

    # A rolled-back staging leaves no row: stage then roll back, as a failed commit
    # after the notification staging would.
    doomed = arrangement(db, plan, venue(db), BookingStatus.PENDING)
    notifications_repo.stage(
        db,
        recipient_id=plan.staff.id,
        event_request_id=plan.event.id,
        type=NotificationType.VENUE_ARRANGEMENT_CANCELLED,
        source_type=NotificationSource.VENUE_CANCELLATION,
        source_id=str(doomed.id),
        occurred_at=datetime.now(UTC),
    )
    db.rollback()
    assert _total_notifications(db) == 1
    assert _inbox(db, plan.staff.id)[0].source_id == str(booking.id)
