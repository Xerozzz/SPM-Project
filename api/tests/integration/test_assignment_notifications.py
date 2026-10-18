"""SCRUM-102: affected users are notified of assignment and reassignment.

TC-102-01 proves initial assignment notifies the incoming coordinator and the
owning organiser once each. TC-102-02 proves reassignment notifies incoming,
outgoing and organiser once each. TC-102-03 proves a multi-role account gets one
row, not one per role. TC-102-04 proves unrelated users get none. TC-102-05
proves every row names the event, the action type, the current owner and one
shared timezone-aware action time. TC-102-06 proves refused changes create none.
TC-102-07 proves retrying the same history action cannot duplicate rows.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from domain.notifications import NotificationSource, NotificationType
from models.event_request import EventRequest
from models.notification import Notification
from models.user import User
from repositories import coordinator_assignments as history_repo
from repositories import notifications as notifications_repo
from services import event_requests as service
from tests.integration.test_submit_event_request import MakeClient, MakeUser, make_draft


def _submitted(db: Session, organiser: User) -> EventRequest:
    """A Submitted request arranged directly, so tests control assignment exactly."""
    request = make_draft(db, organiser)
    request.status = EventStatus.SUBMITTED
    request.submitted_at = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
    db.flush()
    return request


def _assigned(
    db: Session, organiser: User, owner: User, lead: User
) -> tuple[EventRequest, datetime]:
    """A Submitted request owned by `owner`, assigned through the service so the
    first history entry and its notifications exist exactly as the API creates them."""
    request = _submitted(db, organiser)
    assigned_at = datetime(2026, 4, 2, 9, 0, tzinfo=UTC)
    service.assign_coordinator(db, request.id, owner.id, assigned_at, lead.id)
    return request, assigned_at


def _inbox(db: Session, user_id: uuid.UUID) -> list[Notification]:
    return notifications_repo.list_for_recipient(db, user_id)


def _total(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Notification)) or 0


# ------------------------------------------------------------------ TC-102-01


@pytest.mark.story("SCRUM-102")
async def test_initial_assignment_notifies_coordinator_and_organiser(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1: distinct organiser and incoming coordinator → exactly two rows, one
    per inbox, both unread."""
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    lead = make_user("coordinator_lead")
    request = _submitted(db, organiser)

    async with make_client(lead) as client:
        response = await client.post(
            f"/api/event-requests/{request.id}/assign",
            json={"coordinator_id": str(coordinator.id)},
        )

    assert response.status_code == 200
    assert _total(db) == 2
    for recipient in (coordinator, organiser):
        rows = _inbox(db, recipient.id)
        assert len(rows) == 1
        assert rows[0].event_request_id == request.id
        assert rows[0].type == NotificationType.COORDINATOR_ASSIGNED
        assert rows[0].viewed_at is None


# ------------------------------------------------------------------ TC-102-02


@pytest.mark.story("SCRUM-102")
async def test_reassignment_notifies_incoming_outgoing_and_organiser(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC2: distinct organiser, outgoing and incoming coordinators → exactly three
    new rows for the reassignment action, one per inbox."""
    organiser = make_user("organiser")
    outgoing = make_user("coordinator")
    incoming = make_user("coordinator")
    lead = make_user("coordinator_lead")
    request, _ = _assigned(db, organiser, outgoing, lead)
    before = _total(db)
    assert before == 2

    async with make_client(lead) as client:
        response = await client.post(
            f"/api/event-requests/{request.id}/reassign",
            json={
                "coordinator_id": str(incoming.id),
                "expected_current_coordinator_id": str(outgoing.id),
            },
        )

    assert response.status_code == 200
    assert _total(db) == before + 3
    history = history_repo.list_for_event(db, request.id)
    assert len(history) == 2
    source_id = str(history[-1].id)
    for recipient in (incoming, outgoing, organiser):
        rows = [row for row in _inbox(db, recipient.id) if row.source_id == source_id]
        assert len(rows) == 1
        assert rows[0].type == NotificationType.COORDINATOR_REASSIGNED
        assert rows[0].viewed_at is None


# ------------------------------------------------------------------ TC-102-03


@pytest.mark.story("SCRUM-102")
def test_overlapping_roles_receive_one_notification(db: Session, make_user: MakeUser) -> None:
    """AC6: one account is both organiser and incoming coordinator → the recipient
    set deduplicates by account id, so it gets one row, not two."""
    organiser_coordinator = make_user("organiser", "coordinator")
    lead = make_user("coordinator_lead")
    request = _submitted(db, organiser_coordinator)

    service.assign_coordinator(
        db, request.id, organiser_coordinator.id, datetime(2026, 4, 2, 9, 0, tzinfo=UTC), lead.id
    )

    assert _total(db) == 1
    assert len(_inbox(db, organiser_coordinator.id)) == 1


@pytest.mark.story("SCRUM-102")
def test_reassignment_with_overlapping_roles_stays_deduplicated(
    db: Session, make_user: MakeUser
) -> None:
    """AC6: the organiser is also the outgoing coordinator → incoming, organiser
    and outgoing collapse to two rows for two distinct accounts."""
    organiser_outgoing = make_user("organiser", "coordinator")
    incoming = make_user("coordinator")
    lead = make_user("coordinator_lead")
    request, _ = _assigned(db, organiser_outgoing, organiser_outgoing, lead)
    assert _total(db) == 1

    service.reassign_coordinator(
        db,
        request.id,
        incoming.id,
        organiser_outgoing.id,
        lead.id,
        datetime(2026, 4, 3, 9, 0, tzinfo=UTC),
    )

    assert _total(db) == 1 + 2
    history = history_repo.list_for_event(db, request.id)
    source_id = str(history[-1].id)
    outgoing_rows = [row for row in _inbox(db, organiser_outgoing.id) if row.source_id == source_id]
    incoming_rows = [row for row in _inbox(db, incoming.id) if row.source_id == source_id]
    assert len(outgoing_rows) == 1
    assert len(incoming_rows) == 1


# ------------------------------------------------------------------ TC-102-04


@pytest.mark.story("SCRUM-102")
def test_unrelated_users_receive_no_notification(db: Session, make_user: MakeUser) -> None:
    """AC4: other organisers, coordinators and Leads get no row for the action."""
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    lead = make_user("coordinator_lead")
    other_organiser = make_user("organiser")
    other_coordinator = make_user("coordinator")
    other_lead = make_user("coordinator_lead")
    request = _submitted(db, organiser)

    service.assign_coordinator(
        db, request.id, coordinator.id, datetime(2026, 4, 2, 9, 0, tzinfo=UTC), lead.id
    )

    assert _total(db) == 2
    for unrelated in (other_organiser, other_coordinator, other_lead):
        assert _inbox(db, unrelated.id) == []


# ------------------------------------------------------------------ TC-102-05


@pytest.mark.story("SCRUM-102")
def test_notification_identifies_event_action_owner_and_time(
    db: Session, make_user: MakeUser
) -> None:
    """AC3: every recipient row names the event, the reassignment action, the new
    current owner (via the history row) and one shared timezone-aware action time."""
    organiser = make_user("organiser")
    outgoing = make_user("coordinator")
    incoming = make_user("coordinator")
    lead = make_user("coordinator_lead")
    request, _ = _assigned(db, organiser, outgoing, lead)
    acted_at = datetime(2026, 4, 3, 9, 0, tzinfo=UTC)

    service.reassign_coordinator(db, request.id, incoming.id, outgoing.id, lead.id, acted_at)

    history = history_repo.list_for_event(db, request.id)
    entry = history[-1]
    assert entry.new_coordinator_id == incoming.id
    assert entry.previous_coordinator_id == outgoing.id
    assert entry.assigned_at == acted_at
    rows: list[Notification] = []
    for recipient in (incoming, outgoing, organiser):
        rows.extend(_inbox(db, recipient.id))
    action_rows = [row for row in rows if row.source_id == str(entry.id)]
    assert len(action_rows) == 3
    for row in action_rows:
        assert row.event_request_id == request.id
        assert row.type == NotificationType.COORDINATOR_REASSIGNED
        assert row.source_type == NotificationSource.COORDINATOR_ASSIGNMENT
        assert row.occurred_at == acted_at
        assert row.occurred_at.tzinfo is not None


# ------------------------------------------------------------------ TC-102-06


@pytest.mark.story("SCRUM-102")
async def test_failed_assignment_creates_no_notification(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC5: an invalid candidate is refused and stages nothing."""
    organiser = make_user("organiser")
    not_a_coordinator = make_user("organiser")
    lead = make_user("coordinator_lead")
    request = _submitted(db, organiser)

    async with make_client(lead) as client:
        response = await client.post(
            f"/api/event-requests/{request.id}/assign",
            json={"coordinator_id": str(not_a_coordinator.id)},
        )

    assert response.status_code == 422
    assert _total(db) == 0
    assert history_repo.count_for_event(db, request.id) == 0


@pytest.mark.story("SCRUM-102")
async def test_non_lead_assignment_creates_no_notification(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC5: authorisation runs before any write, so a non-Lead attempt stages nothing."""
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = _submitted(db, organiser)

    async with make_client(coordinator) as client:
        response = await client.post(
            f"/api/event-requests/{request.id}/assign",
            json={"coordinator_id": str(coordinator.id)},
        )

    assert response.status_code == 403
    assert _total(db) == 0


@pytest.mark.story("SCRUM-102")
async def test_stale_reassignment_creates_no_notification(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC5: a stale concurrent reassignment is a conflict — the loser stages nothing."""
    organiser = make_user("organiser")
    outgoing = make_user("coordinator")
    first = make_user("coordinator")
    second = make_user("coordinator")
    lead = make_user("coordinator_lead")
    request, _ = _assigned(db, organiser, outgoing, lead)
    before = _total(db)

    async with make_client(lead) as client:
        winner = await client.post(
            f"/api/event-requests/{request.id}/reassign",
            json={
                "coordinator_id": str(first.id),
                "expected_current_coordinator_id": str(outgoing.id),
            },
        )
        stale = await client.post(
            f"/api/event-requests/{request.id}/reassign",
            json={
                "coordinator_id": str(second.id),
                "expected_current_coordinator_id": str(outgoing.id),
            },
        )

    assert winner.status_code == 200
    assert stale.status_code == 409
    assert _total(db) == before + 3
    assert history_repo.count_for_event(db, request.id) == 2


@pytest.mark.story("SCRUM-102")
async def test_same_owner_reassignment_creates_no_notification(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC5: reassigning to the current owner is refused with no new rows."""
    organiser = make_user("organiser")
    owner = make_user("coordinator")
    lead = make_user("coordinator_lead")
    request, _ = _assigned(db, organiser, owner, lead)
    before = _total(db)

    async with make_client(lead) as client:
        response = await client.post(
            f"/api/event-requests/{request.id}/reassign",
            json={
                "coordinator_id": str(owner.id),
                "expected_current_coordinator_id": str(owner.id),
            },
        )

    assert response.status_code == 422
    assert _total(db) == before
    assert history_repo.count_for_event(db, request.id) == 1


# ------------------------------------------------------------------ TC-102-07


@pytest.mark.story("SCRUM-102")
def test_retrying_same_assignment_action_does_not_duplicate(
    db: Session, make_user: MakeUser
) -> None:
    """AC1 idempotence: restaging the same history source collides per recipient
    instead of adding rows (ADR-0022)."""
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    lead = make_user("coordinator_lead")
    request, assigned_at = _assigned(db, organiser, coordinator, lead)
    assert _total(db) == 2
    (entry,) = history_repo.list_for_event(db, request.id)

    for recipient_id in {coordinator.id, organiser.id}:
        notifications_repo.stage(
            db,
            recipient_id=recipient_id,
            event_request_id=request.id,
            type=NotificationType.COORDINATOR_ASSIGNED,
            source_type=NotificationSource.COORDINATOR_ASSIGNMENT,
            source_id=str(entry.id),
            occurred_at=assigned_at,
        )
    db.commit()

    assert _total(db) == 2
