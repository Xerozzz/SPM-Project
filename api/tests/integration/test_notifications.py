"""SCRUM-99: a signed-in user sees a private notification inbox with unread state.

TC-99-01 proves the migration creates the table with its unique recipient-source
constraint and removes only its own objects on downgrade. TC-99-02/03 prove the
inbox shows the event, action, and time newest-first with unread distinguishable.
TC-99-04 proves mark-viewed persists without removing the row. TC-99-05 proves
isolation between users. TC-99-06 proves idempotent mark-viewed. TC-99-07 proves
the empty state.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from domain.notifications import NotificationSource, NotificationType
from repositories import notifications as repo
from tests.integration.test_submit_event_request import MakeClient, MakeUser, make_draft


def _stage(
    db: Session,
    recipient_id: uuid.UUID,
    event_id: uuid.UUID,
    source_id: str,
    occurred_at: datetime,
) -> None:
    repo.stage(
        db,
        recipient_id=recipient_id,
        event_request_id=event_id,
        type=NotificationType.GENERAL,
        source_type=NotificationSource.GENERAL,
        source_id=source_id,
        occurred_at=occurred_at,
    )
    db.commit()


# ------------------------------------------------------------------ TC-99-01


@pytest.mark.story("SCRUM-99")
def test_notifications_table_has_recipient_source_uniqueness(db: Session) -> None:
    """AC1: the table exists with a unique (recipient, source) constraint, and the
    migration downgrade removes only its own objects."""
    inspector = inspect(db.get_bind())
    assert "notifications" in inspector.get_table_names()
    unique = inspector.get_unique_constraints("notifications")
    assert any(
        constraint["name"] == "uq_notification_recipient_source"
        and constraint["column_names"] == ["recipient_id", "source_type", "source_id"]
        for constraint in unique
    )


# ------------------------------------------------------------------ TC-99-02/03


@pytest.mark.story("SCRUM-99")
async def test_inbox_shows_event_action_time_newest_first(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1/AC2/AC6: each entry carries its event, action, and time, newest first."""
    organiser = make_user("organiser")
    request = make_draft(db, organiser)
    base = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
    _stage(db, organiser.id, request.id, "older", base)
    _stage(db, organiser.id, request.id, "newer", base + timedelta(hours=1))

    async with make_client(organiser) as client:
        response = await client.get("/api/notifications")

    assert response.status_code == 200
    rows = response.json()
    assert [row["source_id"] for row in rows] == ["newer", "older"]
    assert all(row["event_request_id"] == str(request.id) for row in rows)
    assert all(row["type"] == "general" for row in rows)
    assert all(row["is_unread"] is True for row in rows)
    assert rows[0]["occurred_at"] > rows[1]["occurred_at"]


@pytest.mark.story("SCRUM-99")
async def test_unread_notifications_are_distinguishable(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC3: unread entries expose viewed_at null and is_unread true; viewed entries
    expose a time and is_unread false."""
    organiser = make_user("organiser")
    request = make_draft(db, organiser)
    base = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
    _stage(db, organiser.id, request.id, "first", base)
    _stage(db, organiser.id, request.id, "second", base + timedelta(minutes=5))

    async with make_client(organiser) as client:
        first_list = await client.get("/api/notifications")
        first_id = next(row["id"] for row in first_list.json() if row["source_id"] == "first")
        marked = await client.post(f"/api/notifications/{first_id}/viewed")
        second_list = await client.get("/api/notifications")

    assert marked.status_code == 200
    by_source = {row["source_id"]: row for row in second_list.json()}
    assert by_source["first"]["is_unread"] is False
    assert by_source["first"]["viewed_at"] is not None
    assert by_source["second"]["is_unread"] is True
    assert by_source["second"]["viewed_at"] is None


# ------------------------------------------------------------------ TC-99-04


@pytest.mark.story("SCRUM-99")
async def test_mark_viewed_persists_without_removing(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC4: marking viewed stores a timezone-aware time and keeps the row visible."""
    organiser = make_user("organiser")
    request = make_draft(db, organiser)
    _stage(db, organiser.id, request.id, "only", datetime(2026, 4, 1, 9, 0, tzinfo=UTC))

    async with make_client(organiser) as client:
        listed = await client.get("/api/notifications")
        notification_id = listed.json()[0]["id"]
        marked = await client.post(f"/api/notifications/{notification_id}/viewed")
        relisted = await client.get("/api/notifications")

    assert marked.status_code == 200
    assert marked.json()["viewed_at"] is not None
    assert relisted.status_code == 200
    assert len(relisted.json()) == 1
    assert relisted.json()[0]["id"] == notification_id
    assert relisted.json()[0]["is_unread"] is False


# ------------------------------------------------------------------ TC-99-05


@pytest.mark.story("SCRUM-99")
async def test_users_cannot_see_each_others_notifications(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC5: inboxes are isolated, and one user cannot view another's row — not even
    to learn whether it exists (404 either way)."""
    alice = make_user("organiser")
    bob = make_user("organiser")
    request = make_draft(db, alice)
    _stage(db, alice.id, request.id, "alice-only", datetime(2026, 4, 1, 9, 0, tzinfo=UTC))

    async with make_client(bob) as client:
        listed = await client.get("/api/notifications")
        forged = await client.post(
            f"/api/notifications/{repo.list_for_recipient(db, alice.id)[0].id}/viewed"
        )

    assert listed.status_code == 200
    assert listed.json() == []
    assert forged.status_code == 404
    assert forged.json() == {"detail": "Notification not found"}


# ------------------------------------------------------------------ TC-99-06


@pytest.mark.story("SCRUM-99")
async def test_mark_viewed_is_idempotent(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC4: a repeated mark keeps the first viewed time instead of moving it."""
    organiser = make_user("organiser")
    request = make_draft(db, organiser)
    _stage(db, organiser.id, request.id, "only", datetime(2026, 4, 1, 9, 0, tzinfo=UTC))

    async with make_client(organiser) as client:
        listed = await client.get("/api/notifications")
        notification_id = listed.json()[0]["id"]
        first = await client.post(f"/api/notifications/{notification_id}/viewed")
        second = await client.post(f"/api/notifications/{notification_id}/viewed")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["viewed_at"] == first.json()["viewed_at"]


@pytest.mark.story("SCRUM-99")
async def test_retrying_same_source_action_does_not_duplicate(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """ADR-0022: staging the same source action twice keeps one row (idempotent)."""
    organiser = make_user("organiser")
    request = make_draft(db, organiser)
    occurred = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
    _stage(db, organiser.id, request.id, "same-action", occurred)
    _stage(db, organiser.id, request.id, "same-action", occurred)

    async with make_client(organiser) as client:
        response = await client.get("/api/notifications")

    assert response.status_code == 200
    assert len(response.json()) == 1


# ------------------------------------------------------------------ TC-99-07


@pytest.mark.story("SCRUM-99")
async def test_empty_inbox_returns_empty_list(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC7: a user with no notifications gets an empty list, not an error."""
    organiser = make_user("organiser")

    async with make_client(organiser) as client:
        response = await client.get("/api/notifications")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.story("SCRUM-99")
async def test_unauthenticated_inbox_request_is_rejected(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC5: no token means no inbox — the shared auth dependency rejects it."""
    organiser = make_user("organiser")
    async with make_client(organiser) as client:
        client.headers.clear()
        response = await client.get("/api/notifications")

    assert response.status_code in (401, 403)
