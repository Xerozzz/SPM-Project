"""SCRUM-49: Venue Staff are notified of a new venue request.

TC-49-01 proves one active Venue Staff member gets exactly one unread notification
with the correct event/action/time. TC-49-02 proves submission still succeeds with
zero Venue Staff. TC-49-03 proves many staff each get exactly one, inactive staff
and other roles get none, and a multi-role staff member gets one, not one per role.
TC-49-04 proves a failed submission creates none.
"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from domain.notifications import NotificationSource, NotificationType
from models.notification import Notification
from repositories import notifications as notifications_repo
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_submit_venue_booking import approved_event, submit
from tests.integration.test_venue_search import make_venue


def _total_notifications(db: Session) -> int:
    """Every stored notification row, whoever the recipient is."""
    return db.scalar(select(func.count()).select_from(Notification)) or 0


def _inbox(db: Session, user_id):  # type: ignore[no-untyped-def]
    return notifications_repo.list_for_recipient(db, user_id)


# ------------------------------------------------------------------ TC-49-01


@pytest.mark.story("SCRUM-49")
async def test_submit_creates_one_unread_notification_for_staff(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1/AC2/AC5: one active Venue Staff, successful submission → exactly one
    unread notification naming the event, the new-request action, and the
    submission time."""
    coordinator = make_user("coordinator")
    staff = make_user("venue_staff")
    event = approved_event(db, make_user("organiser"), coordinator)
    venue = make_venue(db)

    async with make_client(coordinator) as client:
        response = await submit(client, event, venue.id)

    assert response.status_code == 201
    booking_id = response.json()["id"]

    rows = _inbox(db, staff.id)
    assert len(rows) == 1
    row = rows[0]
    assert row.event_request_id == event.id
    assert row.type == NotificationType.VENUE_REQUEST_SUBMITTED
    assert row.source_type == NotificationSource.VENUE_REQUEST
    assert row.source_id == booking_id
    assert row.occurred_at.tzinfo is not None
    assert row.viewed_at is None

    async with make_client(staff) as staff_client:
        inbox = await staff_client.get("/api/notifications")
    assert inbox.status_code == 200
    (entry,) = inbox.json()
    assert entry["event_request_id"] == str(event.id)
    assert entry["type"] == NotificationType.VENUE_REQUEST_SUBMITTED.value
    assert entry["is_unread"] is True


# ------------------------------------------------------------------ TC-49-02


@pytest.mark.story("SCRUM-49")
async def test_submit_succeeds_with_zero_staff_and_zero_notifications(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC4 boundary: no active Venue Staff → submission still succeeds, zero rows."""
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator)
    venue = make_venue(db)

    async with make_client(coordinator) as client:
        response = await submit(client, event, venue.id)

    assert response.status_code == 201
    assert _total_notifications(db) == 0


# ------------------------------------------------------------------ TC-49-03


@pytest.mark.story("SCRUM-49")
async def test_only_active_staff_are_notified_once_each(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1/AC3/AC5: three active staff each get exactly one; inactive staff, the
    coordinator and other roles get none; a multi-role staff member gets one row,
    not one per role."""
    coordinator = make_user("coordinator")
    staff = [make_user("venue_staff") for _ in range(3)]
    multi_role = make_user("venue_staff", "coordinator")
    inactive = make_user("venue_staff", is_active=False)
    lead = make_user("coordinator_lead")
    event = approved_event(db, make_user("organiser"), coordinator)
    venue = make_venue(db)

    async with make_client(coordinator) as client:
        response = await submit(client, event, venue.id)

    assert response.status_code == 201
    assert _total_notifications(db) == 4
    for member in [*staff, multi_role]:
        rows = _inbox(db, member.id)
        assert len(rows) == 1
        assert rows[0].event_request_id == event.id
    assert _inbox(db, inactive.id) == []
    assert _inbox(db, coordinator.id) == []
    assert _inbox(db, lead.id) == []


# ------------------------------------------------------------------ TC-49-04


@pytest.mark.story("SCRUM-49")
async def test_failed_submission_creates_no_notification(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC4: a refused submission (unknown venue) stores zero notification rows."""
    import uuid

    coordinator = make_user("coordinator")
    make_user("venue_staff")
    event = approved_event(db, make_user("organiser"), coordinator)

    async with make_client(coordinator) as client:
        response = await submit(client, event, uuid.uuid4())

    assert response.status_code == 422
    assert _total_notifications(db) == 0
