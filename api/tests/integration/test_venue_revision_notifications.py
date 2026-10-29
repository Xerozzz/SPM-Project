"""SCRUM-127: Venue Staff are notified of a revised (replacement) venue request.

TC-127-01 proves a real revised request through the SCRUM-116 replacement flow gives
each eligible Venue Staff member exactly one unread notification with the correct
event/action/time. TC-127-02 proves zero/one/many routing: no staff still submits
cleanly, many staff each get one, inactive staff and other roles get none, and a
multi-role staff member gets one row. TC-127-03 proves a later distinct revision
notifies again while a retry, an invalid or unauthorised revision, and a rolled-back
staging create none. TC-127-04 proves the Pending revision stays non-occupying and
the item links to the authorised staff view.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from domain.notifications import NotificationSource, NotificationType
from domain.venue_booking import BookingStatus
from models.notification import Notification
from models.venue_booking import VenueBooking
from repositories import notifications as notifications_repo
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_venue_replacement import _affected, _replacement, _request
from tests.integration.test_venue_unavailabilities import make_venue


def _total_notifications(db: Session) -> int:
    """Every stored notification row, whoever the recipient is."""
    return db.scalar(select(func.count()).select_from(Notification)) or 0


def _revision_notifications(db: Session) -> int:
    """Only SCRUM-127 revision rows — the _affected closure setup notifies the
    Coordinator of the closure impact (SCRUM-81), which is out of scope here."""
    return (
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.source_type == NotificationSource.VENUE_REVISION)
        )
        or 0
    )


def _inbox(db: Session, user_id):  # type: ignore[no-untyped-def]
    return notifications_repo.list_for_recipient(db, user_id)


def _revisions(db: Session, user_id):  # type: ignore[no-untyped-def]
    """Only this user's SCRUM-127 revision rows — the Coordinator also holds the
    SCRUM-81 closure-impact notification from the _affected setup."""
    return [
        row for row in _inbox(db, user_id) if row.source_type == NotificationSource.VENUE_REVISION
    ]


# ------------------------------------------------------------------ TC-127-01


@pytest.mark.story("SCRUM-127")
async def test_revised_request_notifies_staff_once_each(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1/AC2: a real revised request via the SCRUM-116 replacement flow → each
    eligible Venue Staff member gets exactly one unread notification naming the
    event, the revision action, and the submission time."""
    original, coordinator = await _affected(db, make_user, make_client)
    staff = next(u for u in db.query(type(coordinator)).all() if "venue_staff" in (u.roles or []))
    other = make_venue(db)

    async with make_client(coordinator) as client:
        response = await _request(client, original, _replacement(original, other.id))

    assert response.status_code == 201, response.text
    revision_id = response.json()["id"]
    assert response.json()["replaces_booking_id"] == str(original.id)

    rows = _inbox(db, staff.id)
    assert len(rows) == 1
    row = rows[0]
    assert row.event_request_id == original.event_request_id
    assert row.type == NotificationType.VENUE_REVISION_SUBMITTED
    assert row.source_type == NotificationSource.VENUE_REVISION
    assert row.source_id == revision_id
    assert row.occurred_at.tzinfo is not None
    assert row.viewed_at is None

    async with make_client(staff) as staff_client:
        inbox = await staff_client.get("/api/notifications")
    assert inbox.status_code == 200
    (entry,) = inbox.json()
    assert entry["event_request_id"] == str(original.event_request_id)
    assert entry["type"] == NotificationType.VENUE_REVISION_SUBMITTED.value
    assert entry["is_unread"] is True


# ------------------------------------------------------------------ TC-127-02


@pytest.mark.story("SCRUM-127")
async def test_revision_succeeds_with_zero_staff_and_zero_notifications(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1 boundary: no active Venue Staff → revision still succeeds, zero rows."""
    original, coordinator = await _affected(db, make_user, make_client)
    for user in db.query(type(coordinator)).all():
        if "venue_staff" in (user.roles or []):
            user.is_active = False
    db.flush()
    other = make_venue(db)

    async with make_client(coordinator) as client:
        response = await _request(client, original, _replacement(original, other.id))

    assert response.status_code == 201, response.text
    assert _revision_notifications(db) == 0


@pytest.mark.story("SCRUM-127")
async def test_only_active_staff_are_notified_once_each(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1/AC3: three active staff each get exactly one; inactive staff, the
    coordinator and other roles get none; a multi-role staff member gets one row,
    not one per role."""
    original, coordinator = await _affected(db, make_user, make_client)
    staff = [make_user("venue_staff"), make_user("venue_staff")]
    multi_role = make_user("venue_staff", "coordinator")
    inactive = make_user("venue_staff", is_active=False)
    lead = make_user("coordinator_lead")
    other = make_venue(db)

    async with make_client(coordinator) as client:
        response = await _request(client, original, _replacement(original, other.id))

    assert response.status_code == 201, response.text
    # _affected creates one venue_staff for the closure; plus the two new staff and
    # the multi-role member = 4 eligible recipients.
    assert _revision_notifications(db) == 4
    seeded = [
        u
        for u in db.query(type(coordinator)).all()
        if "venue_staff" in (u.roles or [])
        and u.is_active
        and u.id not in {*[m.id for m in [*staff, multi_role]], inactive.id}
    ]
    assert len(seeded) == 1
    for member in [*staff, multi_role, *seeded]:
        rows = _inbox(db, member.id)
        assert len(rows) == 1
        assert rows[0].event_request_id == original.event_request_id
        assert rows[0].type == NotificationType.VENUE_REVISION_SUBMITTED
    assert _revisions(db, inactive.id) == []
    assert _revisions(db, coordinator.id) == []
    assert _revisions(db, lead.id) == []


# ------------------------------------------------------------------ TC-127-03


@pytest.mark.story("SCRUM-127")
async def test_later_revision_notifies_again_retry_and_invalid_create_none(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC3: a later distinct revision (after rejecting the first) notifies again; a
    retry collides; an invalid or unauthorised revision and a rolled-back staging
    create none."""
    original, coordinator = await _affected(db, make_user, make_client)
    staff = next(u for u in db.query(type(coordinator)).all() if "venue_staff" in (u.roles or []))
    other = make_venue(db)

    async with make_client(coordinator) as client:
        first = await _request(client, original, _replacement(original, other.id))
        assert first.status_code == 201, first.text
    assert _revision_notifications(db) == 1
    first_id = first.json()["id"]

    # Re-staging the same source action collides on the (recipient, source) key.
    notifications_repo.stage(
        db,
        recipient_id=staff.id,
        event_request_id=original.event_request_id,
        type=NotificationType.VENUE_REVISION_SUBMITTED,
        source_type=NotificationSource.VENUE_REVISION,
        source_id=first_id,
        occurred_at=datetime.now(UTC),
    )
    db.commit()
    assert _revision_notifications(db) == 1

    # An invalid revision (unknown venue) is refused before anything is written.
    import uuid

    async with make_client(coordinator) as client:
        refused = await _request(client, original, _replacement(original, uuid.uuid4()))
        assert refused.status_code == 422
    assert _revision_notifications(db) == 1

    # An unauthorised revision is refused before anything is written.
    async with make_client(make_user("venue_staff")) as outsider:
        forbidden = await _request(outsider, original, _replacement(original, make_venue(db).id))
    assert forbidden.status_code == 403
    assert _revision_notifications(db) == 1

    # Reject the first revision so a later distinct revision is allowed; it notifies
    # again because it is a new replacement row. The unauthorised outsider above is
    # itself active Venue Staff, so the second revision notifies them too.
    async with make_client(staff) as staff_client:
        rejected = await staff_client.post(
            f"/api/venue-bookings/{first_id}/reject", json={"reason": "Too small"}
        )
    assert rejected.status_code == 200, rejected.text
    async with make_client(coordinator) as client:
        second = await _request(client, original, _replacement(original, make_venue(db).id))
        assert second.status_code == 201, second.text
    assert _revision_notifications(db) == 3
    assert _inbox(db, staff.id)[0].source_id == second.json()["id"]

    # A rolled-back staging leaves no row: stage then roll back, as a failed commit
    # after the notification staging would.
    doomed = VenueBooking(
        event_request_id=original.event_request_id,
        venue_id=other.id,
        requested_by_id=coordinator.id,
        session_label=original.session_label,
        start_at=original.start_at,
        end_at=original.end_at,
        effective_start_at=original.effective_start_at,
        effective_end_at=original.effective_end_at,
        status=BookingStatus.PENDING,
        replaces_booking_id=original.id,
    )
    db.add(doomed)
    db.flush()
    notifications_repo.stage(
        db,
        recipient_id=staff.id,
        event_request_id=original.event_request_id,
        type=NotificationType.VENUE_REVISION_SUBMITTED,
        source_type=NotificationSource.VENUE_REVISION,
        source_id=str(doomed.id),
        occurred_at=datetime.now(UTC),
    )
    db.rollback()
    assert _revision_notifications(db) == 3


# ------------------------------------------------------------------ TC-127-04


@pytest.mark.story("SCRUM-127")
async def test_pending_revision_stays_non_occupying_and_links_to_staff_view(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC2: the Pending revision creates no occupancy and the item links to the
    authorised Venue Staff decisions view."""
    staff = make_user("venue_staff")
    original, coordinator = await _affected(db, make_user, make_client)
    other = make_venue(db)

    async with make_client(coordinator) as client:
        response = await _request(client, original, _replacement(original, other.id))
    assert response.status_code == 201, response.text
    revision_id = response.json()["id"]
    assert response.json()["status"] == "pending"

    # The original stays Confirmed; the Pending revision occupies nothing.
    db.refresh(original)
    assert original.status == BookingStatus.CONFIRMED
    revision = db.get(VenueBooking, revision_id)
    assert revision is not None and revision.status == BookingStatus.PENDING

    async with make_client(staff) as staff_client:
        inbox = await staff_client.get("/api/notifications")
    assert inbox.status_code == 200
    (entry,) = inbox.json()
    assert entry["type"] == NotificationType.VENUE_REVISION_SUBMITTED.value
    assert entry["source_type"] == NotificationSource.VENUE_REVISION.value
    assert entry["source_id"] == revision_id
