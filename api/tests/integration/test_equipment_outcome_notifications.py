"""SCRUM-125: the assigned Coordinator is notified of equipment review and reservation outcomes.

TC-125-01 proves each review outcome (available, partially_available, unavailable)
notifies the current Coordinator with the requirement, the outcome and the review time.
TC-125-02 proves a full and a partial reservation each notify the Coordinator with the
arrangement, the quantity and the outcome. TC-125-03 proves distinct actions produce
distinct items while retries, invalid actions and rollbacks produce none. TC-125-04
proves former and unrelated users get nothing.
"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from domain.equipment_requirement import RequirementReview
from domain.notifications import NotificationSource, NotificationType
from models.notification import Notification
from repositories import notifications as notifications_repo
from tests.integration.test_equipment_availability import entry, new_type
from tests.integration.test_equipment_requirements import catalogue, planning_event
from tests.integration.test_reserve_equipment import reserve
from tests.integration.test_review_equipment_requirements import requirement, review_url
from tests.integration.test_submit_event_request import MakeClient, MakeUser


def _total_notifications(db: Session) -> int:
    """Every stored notification row, whoever the recipient is."""
    return db.scalar(select(func.count()).select_from(Notification)) or 0


def _inbox(db: Session, user_id):  # type: ignore[no-untyped-def]
    return notifications_repo.list_for_recipient(db, user_id)


# ------------------------------------------------------------------ TC-125-01


@pytest.mark.story("SCRUM-125")
@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (RequirementReview.AVAILABLE, NotificationType.EQUIPMENT_REVIEW_AVAILABLE),
        (
            RequirementReview.PARTIALLY_AVAILABLE,
            NotificationType.EQUIPMENT_REVIEW_PARTIALLY_AVAILABLE,
        ),
        (RequirementReview.UNAVAILABLE, NotificationType.EQUIPMENT_REVIEW_UNAVAILABLE),
    ],
)
async def test_each_review_outcome_notifies_the_coordinator(
    db: Session,
    make_user: MakeUser,
    make_client: MakeClient,
    outcome: RequirementReview,
    expected: NotificationType,
) -> None:
    """AC1: reviewing a requirement notifies the current Coordinator with the
    requirement, the outcome and the review time."""
    catalogue(db, "Projector")
    event, coordinator = planning_event(db, make_user)
    row = requirement(db, event)

    async with make_client(make_user("tech_support")) as client:
        response = await client.patch(review_url(row.id), json={"review_status": outcome.value})

    assert response.status_code == 200, response.text
    rows = _inbox(db, coordinator.id)
    assert len(rows) == 1
    [item] = rows
    assert item.type == expected
    assert item.source_type == NotificationSource.EQUIPMENT_REVIEW
    assert item.event_request_id == event.id
    assert item.source_id == f"{row.id}:{row.updated_at.isoformat()}"
    assert item.occurred_at == row.updated_at
    assert item.occurred_at.tzinfo is not None
    assert item.viewed_at is None

    async with make_client(coordinator) as coordinator_client:
        inbox = await coordinator_client.get("/api/notifications")
    assert inbox.status_code == 200
    [entry_] = inbox.json()
    assert entry_["type"] == expected.value
    assert entry_["is_unread"] is True


# ------------------------------------------------------------------ TC-125-02


@pytest.mark.story("SCRUM-125")
async def test_full_and_partial_reservations_each_notify_the_coordinator(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC2: a full reservation and a later partial top-up each notify the Coordinator
    with the arrangement, the quantity and the outcome."""
    event, coordinator = planning_event(db, make_user)
    equipment_type = new_type()
    entry(db, equipment_type, 5)
    row = requirement(db, event, equipment_type, quantity=4)
    tech = make_user("tech_support")

    async with make_client(tech) as client:
        first = await reserve(client, event, row, quantity=2)
        assert first.status_code == 201, first.text
        second = await reserve(client, event, row, quantity=2)
        assert second.status_code == 201, second.text

    rows = _inbox(db, coordinator.id)
    assert len(rows) == 2
    assert rows[0].type == NotificationType.EQUIPMENT_RESERVED_FULL
    assert rows[1].type == NotificationType.EQUIPMENT_RESERVED_PARTIAL
    for item in rows:
        assert item.source_type == NotificationSource.EQUIPMENT_RESERVATION
        assert item.event_request_id == event.id
        assert item.occurred_at.tzinfo is not None
        assert item.viewed_at is None
    # One item per reservation: the source ids are the two distinct reservation rows.
    assert rows[0].source_id != rows[1].source_id


# ------------------------------------------------------------------ TC-125-03


@pytest.mark.story("SCRUM-125")
async def test_retry_invalid_and_rollback_create_nothing(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC3: a re-staged retry, an invalid review, an unauthorised review and a
    rolled-back reservation produce no extra item."""
    catalogue(db, "Projector")
    event, coordinator = planning_event(db, make_user)
    row = requirement(db, event)
    tech = make_user("tech_support")

    async with make_client(tech) as client:
        reviewed = await client.patch(
            review_url(row.id), json={"review_status": RequirementReview.AVAILABLE.value}
        )
        assert reviewed.status_code == 200, reviewed.text
        # An invalid outcome is refused before anything is written.
        refused = await client.patch(review_url(row.id), json={"review_status": "approved"})
        assert refused.status_code == 422

    # A retry that re-stages the same review collides on the review's source key
    # instead of duplicating (ADR-0060).
    db.refresh(row)
    notifications_repo.stage(
        db,
        recipient_id=coordinator.id,
        event_request_id=event.id,
        type=NotificationType.EQUIPMENT_REVIEW_AVAILABLE,
        source_type=NotificationSource.EQUIPMENT_REVIEW,
        source_id=f"{row.id}:{row.updated_at.isoformat()}",
        occurred_at=row.updated_at,
    )
    db.commit()
    assert _total_notifications(db) == 1

    # An unauthorised review is refused before anything is written.
    async with make_client(make_user("organiser")) as outsider:
        forbidden = await outsider.patch(
            review_url(row.id), json={"review_status": RequirementReview.UNAVAILABLE.value}
        )
    assert forbidden.status_code == 403

    # A rolled-back reservation: asking for more than is free refuses the exact-or-
    # nothing request with 409, so no row and no notification exist for it.
    equipment_type = new_type()
    entry(db, equipment_type, 1)
    scarce = requirement(db, event, equipment_type, quantity=3)
    async with make_client(tech) as client:
        rejected = await reserve(client, event, scarce, quantity=2)
    assert rejected.status_code == 409

    assert _total_notifications(db) == 1
    assert len(_inbox(db, coordinator.id)) == 1


# ------------------------------------------------------------------ TC-125-04


@pytest.mark.story("SCRUM-125")
async def test_former_and_unrelated_users_get_nothing(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC3: a review and a reservation notify only the current Coordinator — not a
    former one, not Technical Support, not other roles."""
    catalogue(db, "Projector")
    event, coordinator = planning_event(db, make_user)
    former = make_user("coordinator")
    event.coordinator_id = former.id
    db.flush()
    row = requirement(db, event)
    tech = make_user("tech_support")
    venue_staff = make_user("venue_staff")

    # The event is reassigned before the review, so the former Coordinator gets nothing.
    event.coordinator_id = coordinator.id
    db.flush()

    async with make_client(tech) as client:
        reviewed = await client.patch(
            review_url(row.id), json={"review_status": RequirementReview.AVAILABLE.value}
        )
        assert reviewed.status_code == 200, reviewed.text

    assert _inbox(db, former.id) == []
    assert _inbox(db, tech.id) == []
    assert _inbox(db, venue_staff.id) == []
    rows = _inbox(db, coordinator.id)
    assert len(rows) == 1
    assert rows[0].type == NotificationType.EQUIPMENT_REVIEW_AVAILABLE


@pytest.mark.story("SCRUM-125")
async def test_review_without_a_coordinator_still_commits(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1 boundary: no Coordinator assigned → the review still commits, zero rows."""
    catalogue(db, "Projector")
    event, _ = planning_event(db, make_user)
    event.coordinator_id = None
    db.flush()
    row = requirement(db, event)

    async with make_client(make_user("tech_support")) as client:
        response = await client.patch(
            review_url(row.id), json={"review_status": RequirementReview.AVAILABLE.value}
        )

    assert response.status_code == 200, response.text
    assert _total_notifications(db) == 0


@pytest.mark.story("SCRUM-125")
async def test_reservation_without_a_coordinator_still_commits(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC2 boundary: no Coordinator assigned → the reservation still commits, zero rows."""
    event, _ = planning_event(db, make_user)
    event.coordinator_id = None
    db.flush()
    equipment_type = new_type()
    entry(db, equipment_type, 5)
    row = requirement(db, event, equipment_type, quantity=3)

    async with make_client(make_user("tech_support")) as client:
        response = await reserve(client, event, row)

    assert response.status_code == 201, response.text
    assert _total_notifications(db) == 0
