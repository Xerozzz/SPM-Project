"""SCRUM-96: Coordinator Leads are notified of an unassigned submission.

TC-96-01 proves one active Lead gets exactly one unread notification with the
correct event/action/time. TC-96-02 proves submission still succeeds with zero
Leads. TC-96-03 proves many Leads each get exactly one. TC-96-04 proves inactive
Leads and non-Leads get none, and a multi-role Lead gets one, not one per role.
TC-96-05 proves a failed submission creates none. TC-96-06 proves retrying a
completed submission cannot duplicate.
"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from domain.notifications import NotificationSource, NotificationType
from models.notification import Notification
from repositories import notifications as notifications_repo
from tests.integration.test_submit_event_request import MakeClient, MakeUser, make_draft


def _total_notifications(db: Session) -> int:
    """Every stored notification row, whoever the recipient is."""
    return db.scalar(select(func.count()).select_from(Notification)) or 0


def _inbox(db: Session, user_id):  # type: ignore[no-untyped-def]
    return notifications_repo.list_for_recipient(db, user_id)


# ------------------------------------------------------------------ TC-96-01


@pytest.mark.story("SCRUM-96")
async def test_submit_creates_one_unread_notification_for_the_lead(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1/AC2/AC5: one active Lead, successful submission → exactly one unread
    notification naming the event, the unassigned-submission action, and the
    submission time."""
    organiser = make_user("organiser")
    lead = make_user("coordinator_lead")
    draft = make_draft(db, organiser)

    async with make_client(organiser) as client:
        response = await client.post(f"/api/event-requests/{draft.id}/submit")

    assert response.status_code == 200
    db.refresh(draft)
    assert draft.submitted_at is not None

    rows = _inbox(db, lead.id)
    assert len(rows) == 1
    row = rows[0]
    assert row.event_request_id == draft.id
    assert row.type == NotificationType.UNASSIGNED_SUBMISSION
    assert row.source_type == NotificationSource.EVENT_SUBMISSION
    assert row.source_id == str(draft.id)
    assert row.occurred_at == draft.submitted_at
    assert row.occurred_at.tzinfo is not None
    assert row.viewed_at is None

    async with make_client(lead) as lead_client:
        inbox = await lead_client.get("/api/notifications")
    assert inbox.status_code == 200
    (entry,) = inbox.json()
    assert entry["event_request_id"] == str(draft.id)
    assert entry["type"] == NotificationType.UNASSIGNED_SUBMISSION.value
    assert entry["is_unread"] is True


# ------------------------------------------------------------------ TC-96-02


@pytest.mark.story("SCRUM-96")
async def test_submit_succeeds_with_zero_leads_and_zero_notifications(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1 boundary: no active Leads → submission still succeeds, zero rows stored."""
    organiser = make_user("organiser")
    draft = make_draft(db, organiser)

    async with make_client(organiser) as client:
        response = await client.post(f"/api/event-requests/{draft.id}/submit")

    assert response.status_code == 200
    assert _total_notifications(db) == 0


# ------------------------------------------------------------------ TC-96-03


@pytest.mark.story("SCRUM-96")
async def test_each_active_lead_receives_exactly_one_notification(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1/AC5: three active Leads → each inbox holds exactly one row, total three."""
    organiser = make_user("organiser")
    leads = [make_user("coordinator_lead") for _ in range(3)]
    draft = make_draft(db, organiser)

    async with make_client(organiser) as client:
        response = await client.post(f"/api/event-requests/{draft.id}/submit")

    assert response.status_code == 200
    assert _total_notifications(db) == 3
    for lead in leads:
        rows = _inbox(db, lead.id)
        assert len(rows) == 1
        assert rows[0].event_request_id == draft.id


# ------------------------------------------------------------------ TC-96-04


@pytest.mark.story("SCRUM-96")
async def test_only_active_leads_are_notified_once_each(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC3/AC5: inactive Leads, coordinators and other roles get none; a multi-role
    active Lead gets one row, not one per role."""
    organiser = make_user("organiser")
    active_lead = make_user("coordinator_lead")
    multi_role_lead = make_user("coordinator_lead", "coordinator")
    inactive_lead = make_user("coordinator_lead", is_active=False)
    coordinator = make_user("coordinator")
    venue_staff = make_user("venue_staff")
    draft = make_draft(db, organiser)

    async with make_client(organiser) as client:
        response = await client.post(f"/api/event-requests/{draft.id}/submit")

    assert response.status_code == 200
    assert len(_inbox(db, active_lead.id)) == 1
    assert len(_inbox(db, multi_role_lead.id)) == 1
    assert _inbox(db, inactive_lead.id) == []
    assert _inbox(db, coordinator.id) == []
    assert _inbox(db, venue_staff.id) == []
    assert _total_notifications(db) == 2


# ------------------------------------------------------------------ TC-96-05


@pytest.mark.story("SCRUM-96")
async def test_failed_submission_creates_no_notification(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC4: an incomplete draft is refused and stores zero notification rows."""
    organiser = make_user("organiser")
    make_user("coordinator_lead")
    draft = make_draft(db, organiser, name=None, expected_attendance=None)

    async with make_client(organiser) as client:
        response = await client.post(f"/api/event-requests/{draft.id}/submit")

    assert response.status_code == 422
    assert _total_notifications(db) == 0


# ------------------------------------------------------------------ TC-96-06


@pytest.mark.story("SCRUM-96")
async def test_resubmitting_a_completed_request_creates_no_second_notification(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC5: retrying the same already-completed submission is refused and keeps
    exactly one row per eligible Lead (deduplicated by the source identity)."""
    organiser = make_user("organiser")
    lead = make_user("coordinator_lead")
    draft = make_draft(db, organiser)

    async with make_client(organiser) as client:
        first = await client.post(f"/api/event-requests/{draft.id}/submit")
        second = await client.post(f"/api/event-requests/{draft.id}/submit")

    assert first.status_code == 200
    assert second.status_code == 409
    assert len(_inbox(db, lead.id)) == 1
    assert _total_notifications(db) == 1
