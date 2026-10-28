"""SCRUM-120: confirmation, return to planning and cancellation, read through
GET /event-requests/{id}/history.

Every record is made by its real writer: SCRUM-80 confirms, SCRUM-47 approves a change,
SCRUM-118 starts a venue change, SCRUM-132 saves a closure, SCRUM-115 cancels. Access is
the SCRUM-88 route's, unchanged (ADR-0062, ADR-0067).
"""

import uuid
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy.orm import Session

from domain.change_decision import Decision
from domain.roles import Role
from domain.safety_review import SafetyDecision, fingerprint
from models.event_change_request import EventChangeRequest
from models.event_request import EventRequest
from models.user import User
from models.venue_booking import VenueBooking
from services import event_cancellations, event_confirmations, venue_changes
from services import safety_reviews as safety_service
from tests.integration.test_closure_replanning import _close
from tests.integration.test_safety_approval_invalidation import (
    _confirmed,
    _decide,
    _session_change,
)
from tests.integration.test_safety_review import _NOW
from tests.integration.test_submit_event_request import MakeClient, MakeUser

REASON = "Funding withdrawn"
_LATER = _NOW + timedelta(minutes=5)


async def history(make_client: MakeClient, viewer: User, event: EventRequest) -> Any:
    async with make_client(viewer) as client:
        response = await client.get(f"/api/event-requests/{event.id}/history")
    assert response.status_code == 200
    return response.json()


def of(body: list[dict[str, Any]], action: str) -> list[dict[str, Any]]:
    return [e for e in body if e["action"] == action]


def owner_of(db: Session, event: EventRequest) -> User:
    owner = db.get(User, event.organiser_id)
    assert owner is not None
    return owner


def replanned_by_change(
    db: Session, make_user: MakeUser
) -> tuple[EventRequest, VenueBooking, User, uuid.UUID]:
    """Confirmed at _NOW, then a change approved at _NOW sends it back to planning."""
    event, booking, coordinator = _confirmed(db, make_user)
    change_id = _session_change(db, event, booking)
    _decide(db, event, change_id, coordinator, Decision.APPROVE)
    return event, booking, coordinator, change_id


# ------------------------------------------------------------------ AC3 confirmation


@pytest.mark.story("SCRUM-120")
async def test_a_confirmation_shows_the_coordinator_and_time(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator = _confirmed(db, make_user)

    [entry] = of(await history(make_client, coordinator, event), "event_confirmed")

    assert (entry["actor_email"], entry["occurred_at"]) == (
        coordinator.email,
        _NOW.isoformat().replace("+00:00", "Z"),
    )
    assert entry["actor_recorded"] is True


@pytest.mark.story("SCRUM-120")
async def test_only_the_latest_confirmation_is_shown_after_a_reconfirmation(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """The ADR-0062 gap, pinned: confirming again overwrites the earlier confirmation."""
    event, _, coordinator, _ = replanned_by_change(db, make_user)
    plan = safety_service.plan_of(db, event, _LATER)
    officer = make_user(Role.SAFETY_OFFICER.value)
    safety_service.record(
        db, event, SafetyDecision.APPROVE, "Checked again", fingerprint(plan), officer.id, _LATER
    )
    event_confirmations.confirm(db, event, coordinator.id, _LATER)

    body = await history(make_client, coordinator, event)

    assert [e["occurred_at"][:19] for e in of(body, "event_confirmed")] == [_LATER.isoformat()[:19]]
    assert len(of(body, "returned_to_planning")) == 1


# ------------------------------------------------------------ AC3 return to planning


@pytest.mark.story("SCRUM-120")
async def test_an_approved_change_returns_the_event_with_the_deciders_name(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator, _ = replanned_by_change(db, make_user)

    [entry] = of(await history(make_client, coordinator, event), "returned_to_planning")

    assert (entry["replan_cause"], entry["actor_email"], entry["actor_recorded"]) == (
        "change_request",
        coordinator.email,
        True,
    )
    assert entry["source_type"] == "safety_review"
    # The decision has no entry of its own yet (SCRUM-120 PR 2), so nothing to link.
    assert entry["related_entry_ids"] == []


@pytest.mark.story("SCRUM-120")
async def test_a_venue_change_return_links_the_cancelled_arrangement(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, booking, coordinator = _confirmed(db, make_user)
    venue_changes.cancel_for_venue_change(
        db, event.id, booking.id, coordinator.id, "Hall flooded", True, _LATER
    )

    body = await history(make_client, coordinator, event)

    [entry] = of(body, "returned_to_planning")
    assert (entry["replan_cause"], entry["actor_email"]) == (
        "venue_cancellation",
        coordinator.email,
    )
    [cancelled] = of(body, "arrangement_cancelled")
    assert entry["related_entry_ids"] == [cancelled["id"]]
    assert body.index(cancelled) < body.index(entry)


@pytest.mark.story("SCRUM-120")
async def test_a_closure_return_names_the_venue_staff_member(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, booking, coordinator = _confirmed(db, make_user)
    staff = make_user("venue_staff")
    _close(db, booking, staff)

    [entry] = of(await history(make_client, coordinator, event), "returned_to_planning")

    assert (entry["replan_cause"], entry["actor_email"], entry["actor_recorded"]) == (
        "venue_closure",
        staff.email,
        True,
    )


@pytest.mark.story("SCRUM-120")
async def test_without_a_cause_at_exactly_that_time_the_actor_is_not_recorded(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """Never guessed: a cause a microsecond away does not lend its actor (ADR-0067)."""
    event, _, coordinator, change_id = replanned_by_change(db, make_user)
    change = db.get(EventChangeRequest, change_id)
    assert change is not None and change.decided_at is not None
    change.decided_at += timedelta(microseconds=1)
    db.flush()

    [entry] = of(await history(make_client, coordinator, event), "returned_to_planning")

    assert (entry["actor_id"], entry["actor_email"], entry["actor_recorded"]) == (
        None,
        None,
        False,
    )
    assert entry["replan_cause"] == "change_request"


# ------------------------------------------------------------------ AC6 cancellation


def cancelled(db: Session, make_user: MakeUser) -> tuple[EventRequest, User]:
    """A Confirmed event, with a held venue and reserved equipment, cancelled at _LATER."""
    event, _, coordinator = _confirmed(db, make_user)
    event_cancellations.cancel(db, event.id, coordinator.id, REASON, None, _LATER)
    return event, coordinator


@pytest.mark.story("SCRUM-120")
async def test_a_cancellation_is_shown_once_and_links_what_it_released(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, coordinator = cancelled(db, make_user)

    body = await history(make_client, coordinator, event)

    [entry] = of(body, "event_cancelled")
    assert (entry["actor_email"], entry["reason"]) == (coordinator.email, REASON)
    released = of(body, "arrangement_cancelled") + of(body, "reservation_released")
    assert len(released) == 2
    assert sorted(entry["related_entry_ids"]) == sorted(e["id"] for e in released)
    # Linked, not repeated: every id is still in the history exactly once.
    ids = [e["id"] for e in body]
    assert len(ids) == len(set(ids))


# ------------------------------------------------------- AC7 access, privacy, no writes


def every_lifecycle_entry(db: Session, make_user: MakeUser) -> tuple[EventRequest, User]:
    """Confirmed, returned to planning by a change, then cancelled."""
    event, _, coordinator, _ = replanned_by_change(db, make_user)
    event_cancellations.cancel(db, event.id, coordinator.id, REASON, None, _LATER)
    return event, coordinator


@pytest.mark.story("SCRUM-120")
async def test_owner_assignee_and_lead_see_the_same_lifecycle_entries(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, coordinator = every_lifecycle_entry(db, make_user)

    bodies = [
        await history(make_client, viewer, event)
        for viewer in (owner_of(db, event), coordinator, make_user("coordinator_lead"))
    ]

    new = {"event_confirmed", "returned_to_planning", "event_cancelled"}
    assert {e["action"] for e in bodies[0]} >= new
    assert all(body == bodies[0] for body in bodies)


@pytest.mark.story("SCRUM-120")
@pytest.mark.parametrize(
    "caller_kind", ["coordinator", "organiser", "safety_officer", "venue_staff", "attendee"]
)
async def test_everyone_else_still_gets_a_bare_403(
    caller_kind: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = every_lifecycle_entry(db, make_user)

    async with make_client(make_user(caller_kind)) as client:
        response = await client.get(f"/api/event-requests/{event.id}/history")

    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}


@pytest.mark.story("SCRUM-120")
async def test_reading_the_lifecycle_entries_issues_only_selects(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, coordinator = every_lifecycle_entry(db, make_user)
    viewers = (owner_of(db, event), coordinator, make_user("coordinator_lead"))
    db.flush()
    statements: list[str] = []
    flushes: list[object] = []

    def capture(_conn: object, _cursor: object, statement: str, *_args: object) -> None:
        statements.append(statement)

    def count_flush(*_args: object) -> None:
        flushes.append(object())

    connection = db.connection()
    sa_event.listen(connection, "before_cursor_execute", capture)
    sa_event.listen(db, "before_flush", count_flush)
    try:
        for viewer in viewers:
            await history(make_client, viewer, event)
    finally:
        sa_event.remove(connection, "before_cursor_execute", capture)
        sa_event.remove(db, "before_flush", count_flush)

    assert statements
    assert all(s.lstrip().upper().startswith("SELECT") for s in statements)
    assert flushes == []
