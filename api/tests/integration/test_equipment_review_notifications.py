"""SCRUM-124: Technical Support Staff are notified of equipment requirements needing review.

TC-124-01 proves a new requirement and a later change produce distinct items naming the
event, the requirement, the add/change action and the change time. TC-124-02 proves
zero/one/many recipients, inactive users and overlapping roles follow the fallback and
dedup rules. TC-124-03 proves a retry, an invalid edit, an unauthorised edit and a
rolled-back change produce no extra item and reserve no stock.
"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from domain.notifications import NotificationSource, NotificationType
from models.equipment import Equipment
from models.notification import Notification
from repositories import notifications as notifications_repo
from tests.integration.test_equipment_requirements import (
    audit,
    body,
    catalogue,
    planning_event,
    url,
)
from tests.integration.test_submit_event_request import MakeClient, MakeUser


def _total_notifications(db: Session) -> int:
    """Every stored notification row, whoever the recipient is."""
    return db.scalar(select(func.count()).select_from(Notification)) or 0


def _inbox(db: Session, user_id):  # type: ignore[no-untyped-def]
    return notifications_repo.list_for_recipient(db, user_id)


# ------------------------------------------------------------------ TC-124-01


@pytest.mark.story("SCRUM-124")
async def test_add_and_later_change_produce_distinct_items(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1/AC2: a new requirement alerts eligible Technical Support Staff with the
    event, the requirement, the add action and the change time; a later change on
    the same requirement produces another, distinct item."""
    catalogue(db, "Projector")
    event, coordinator = planning_event(db, make_user)
    staff = make_user("tech_support")

    async with make_client(coordinator) as client:
        added = await client.post(url(event), json=body())
        assert added.status_code == 201, added.text
        requirement_id = added.json()["id"]
        changed = await client.patch(url(event, f"/{requirement_id}"), json={"quantity": 5})
        assert changed.status_code == 200, changed.text

    rows = _inbox(db, staff.id)
    assert len(rows) == 2
    assert rows[0].event_request_id == event.id
    assert rows[1].event_request_id == event.id
    for row in rows:
        assert row.type == NotificationType.EQUIPMENT_REVIEW_NEEDED
        assert row.source_type == NotificationSource.EQUIPMENT_REQUIREMENT_CHANGE
        assert row.occurred_at.tzinfo is not None
        assert row.viewed_at is None
    # One item per change: the source ids are the two distinct audit rows.
    changes = audit(db, event)
    assert len(changes) == 2
    assert {rows[0].source_id, rows[1].source_id} == {str(changes[0].id), str(changes[1].id)}
    assert rows[0].source_id != rows[1].source_id

    async with make_client(staff) as staff_client:
        inbox = await staff_client.get("/api/notifications")
    assert inbox.status_code == 200
    entries = inbox.json()
    assert len(entries) == 2
    assert all(entry["is_unread"] is True for entry in entries)
    assert all(entry["type"] == NotificationType.EQUIPMENT_REVIEW_NEEDED.value for entry in entries)


# ------------------------------------------------------------------ TC-124-02


@pytest.mark.story("SCRUM-124")
async def test_add_succeeds_with_zero_staff_and_zero_notifications(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1 boundary: no eligible Technical Support Staff → the add still succeeds,
    zero rows."""
    catalogue(db, "Projector")
    event, coordinator = planning_event(db, make_user)

    async with make_client(coordinator) as client:
        response = await client.post(url(event), json=body())

    assert response.status_code == 201
    assert _total_notifications(db) == 0


@pytest.mark.story("SCRUM-124")
async def test_only_active_tech_support_are_notified_once_each(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1/AC3: three active staff each get exactly one; inactive staff, the
    coordinator and other roles get none; a multi-role member gets one row,
    not one per role."""
    catalogue(db, "Projector")
    event, coordinator = planning_event(db, make_user)
    staff = [make_user("tech_support") for _ in range(3)]
    multi_role = make_user("tech_support", "coordinator")
    inactive = make_user("tech_support", is_active=False)
    venue_staff = make_user("venue_staff")

    async with make_client(coordinator) as client:
        response = await client.post(url(event), json=body())

    assert response.status_code == 201
    assert _total_notifications(db) == 4
    for member in [*staff, multi_role]:
        rows = _inbox(db, member.id)
        assert len(rows) == 1
        assert rows[0].event_request_id == event.id
    assert _inbox(db, inactive.id) == []
    assert _inbox(db, coordinator.id) == []
    assert _inbox(db, venue_staff.id) == []


# ------------------------------------------------------------------ TC-124-03


@pytest.mark.story("SCRUM-124")
async def test_retry_invalid_unauthorised_and_rollback_create_nothing(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC3: a re-staged retry, an invalid edit, an unauthorised edit and a
    rolled-back change produce no extra item and reserve no stock."""
    catalogue(db, "Projector")
    event, coordinator = planning_event(db, make_user)
    staff = make_user("tech_support")
    before = [(e.id, e.total_quantity, e.is_active) for e in db.scalars(select(Equipment))]

    async with make_client(coordinator) as client:
        added = await client.post(url(event), json=body())
        assert added.status_code == 201, added.text
        requirement_id = added.json()["id"]
        # An invalid edit is refused before anything is written.
        refused = await client.patch(url(event, f"/{requirement_id}"), json={"quantity": -1})
        assert refused.status_code == 422

    # A retry that re-stages the same change collides on the audit row's source
    # key instead of duplicating (ADR-0060).
    changes = audit(db, event)
    assert len(changes) == 1
    notifications_repo.stage(
        db,
        recipient_id=staff.id,
        event_request_id=event.id,
        type=NotificationType.EQUIPMENT_REVIEW_NEEDED,
        source_type=NotificationSource.EQUIPMENT_REQUIREMENT_CHANGE,
        source_id=str(changes[0].id),
        occurred_at=changes[0].changed_at,
    )
    db.commit()
    assert _total_notifications(db) == 1

    # An unauthorised edit is refused before anything is written.
    async with make_client(make_user("organiser")) as outsider:
        forbidden = await outsider.patch(url(event, f"/{requirement_id}"), json={"quantity": 7})
    assert forbidden.status_code == 403

    # A rolled-back change: a duplicate add fails the one-live-line-per-type index,
    # so the staged notification rolls back with it.
    async with make_client(coordinator) as client:
        duplicate = await client.post(url(event), json=body())
    assert duplicate.status_code == 422

    assert _total_notifications(db) == 1
    assert len(_inbox(db, staff.id)) == 1
    db.expire_all()
    assert [(e.id, e.total_quantity, e.is_active) for e in db.scalars(select(Equipment))] == before
    changes = audit(db, event)
    assert len(changes) == 1
    assert _inbox(db, staff.id)[0].source_id == str(changes[0].id)
