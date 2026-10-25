"""Registration-status notifications reuse the private SCRUM-99 inbox."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.notifications import NotificationSource, NotificationType
from models.notification import Notification
from services import registration_intake
from tests.integration.test_event_registrations import open_event, submission
from tests.integration.test_registration_intake import confirmed_event
from tests.integration.test_submit_event_request import MakeClient, MakeUser


def notifications_for(db: Session, recipient_id: object) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification)
            .where(Notification.recipient_id == recipient_id)
            .order_by(Notification.occurred_at, Notification.id)
        )
    )


def registration_notifications_for(db: Session, recipient_id: object) -> list[Notification]:
    return [
        row
        for row in notifications_for(db, recipient_id)
        if row.source_type is NotificationSource.REGISTRATION_STATUS
    ]


@pytest.mark.story("SCRUM-51")
async def test_submission_and_withdrawal_notify_only_the_affected_attendee_once(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser = open_event(db, make_user)
    attendee = make_user("attendee", "organiser")

    async with make_client(attendee) as client:
        created = await client.post(
            f"/api/attendee/events/{event.id}/registrations", json=submission()
        )
        withdrawn = await client.post(f"/api/attendee/events/{event.id}/registration/withdraw")
        repeated = await client.post(f"/api/attendee/events/{event.id}/registration/withdraw")
        replacement = await client.post(
            f"/api/attendee/events/{event.id}/registrations", json=submission({"age": 25})
        )

    assert created.status_code == 201
    assert withdrawn.status_code == repeated.status_code == 200
    assert replacement.status_code == 201
    assert repeated.json()["already_withdrawn"] is True
    attendee_rows = registration_notifications_for(db, attendee.id)
    assert [(row.type, row.source_type) for row in attendee_rows] == [
        (NotificationType.REGISTRATION_PENDING, NotificationSource.REGISTRATION_STATUS),
        (NotificationType.REGISTRATION_WITHDRAWN, NotificationSource.REGISTRATION_STATUS),
        (NotificationType.REGISTRATION_PENDING, NotificationSource.REGISTRATION_STATUS),
    ]
    assert all(row.event_request_id == event.id for row in attendee_rows)
    assert all(row.viewed_at is None for row in attendee_rows)
    assert len({row.source_id for row in attendee_rows}) == 3
    assert registration_notifications_for(db, organiser.id) == []


@pytest.mark.story("SCRUM-51")
@pytest.mark.parametrize(
    ("target", "kind"),
    [
        ("accepted", NotificationType.REGISTRATION_ACCEPTED),
        ("waitlisted", NotificationType.REGISTRATION_WAITLISTED),
    ],
)
async def test_committed_organiser_decision_notifies_only_its_attendee(
    db: Session,
    make_user: MakeUser,
    make_client: MakeClient,
    target: str,
    kind: NotificationType,
) -> None:
    event, organiser, coordinator = confirmed_event(db, make_user)
    registration_intake.open_intake(db, event.id, None, datetime.now(UTC))
    attendee = make_user("attendee")
    async with make_client(attendee) as client:
        created = await client.post(
            f"/api/attendee/events/{event.id}/registrations", json=submission()
        )
    registration_id = created.json()["id"]

    async with make_client(organiser) as client:
        changed = await client.post(
            f"/api/event-requests/{event.id}/registrations/{registration_id}/decision",
            json={"expected_status": "pending", "status": target, "note": "Capacity reviewed"},
        )
        repeated = await client.post(
            f"/api/event-requests/{event.id}/registrations/{registration_id}/decision",
            json={"expected_status": "pending", "status": target, "note": "Capacity reviewed"},
        )

    assert changed.status_code == repeated.status_code == 200
    attendee_rows = registration_notifications_for(db, attendee.id)
    assert [row.type for row in attendee_rows] == [NotificationType.REGISTRATION_PENDING, kind]
    assert attendee_rows[-1].occurred_at.tzinfo is not None
    assert len({row.source_id for row in attendee_rows}) == 2
    assert registration_notifications_for(db, organiser.id) == []
    assert registration_notifications_for(db, coordinator.id) == []


@pytest.mark.story("SCRUM-51")
async def test_refused_submission_creates_no_registration_notification(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = open_event(db, make_user)
    attendee = make_user("attendee")

    async with make_client(attendee) as client:
        refused = await client.post(
            f"/api/attendee/events/{event.id}/registrations", json=submission({"full_name": " "})
        )

    assert refused.status_code == 422
    assert notifications_for(db, attendee.id) == []
