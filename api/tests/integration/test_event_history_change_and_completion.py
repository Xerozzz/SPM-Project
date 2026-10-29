"""SCRUM-120: change requests and completion, read through GET /event-requests/{id}/history.

Every record is made by its real writer: SCRUM-37 submits a change, SCRUM-47 decides it,
SCRUM-86 completes the event and corrects its closure record. Access is the SCRUM-88
route's, unchanged; the Lead now sees change requests too (ADR-0068).
"""

import uuid
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy.orm import Session

from domain.change_decision import Decision
from models.event_request import EventRequest
from models.user import User
from models.venue_booking import VenueBooking
from schemas.event_change_requests import EventChangeRequestCreate
from services import event_change_requests as change_service
from services import event_completions
from tests.integration.test_event_history_lifecycle import history, of, owner_of
from tests.integration.test_safety_approval_invalidation import (
    _confirmed,
    _decide,
    _session_change,
)
from tests.integration.test_safety_review import _NOW
from tests.integration.test_submit_event_request import MakeClient, MakeUser


def _longer(db: Session, event: EventRequest) -> uuid.UUID:
    """The Organiser asks for the event to end an hour later; left pending."""
    assert event.end_at is not None
    body = {
        "submission_key": str(uuid.uuid4()),
        "reason": "Panel added",
        "event": {"end_at": (event.end_at + timedelta(hours=1)).isoformat()},
    }
    proposal = EventChangeRequestCreate.model_validate(body).to_proposal()
    created, _ = change_service.submit(
        db, event.id, event.organiser_id, proposal, uuid.uuid4(), _NOW
    )
    return created.id


def _label(db: Session, booking: VenueBooking) -> str:
    db.refresh(booking)
    return booking.session_label


# ------------------------------------------------------------ AC1 change requests


@pytest.mark.story("SCRUM-120")
async def test_a_request_and_its_approval_show_who_why_and_the_values(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, booking, coordinator = _confirmed(db, make_user)
    old_label = _label(db, booking)
    change_id = _session_change(db, event, booking)
    _decide(db, event, change_id, coordinator, Decision.APPROVE)
    owner = owner_of(db, event)

    body = await history(make_client, owner, event)

    [requested] = of(body, "change_requested")
    assert (requested["actor_email"], requested["reason"]) == (
        owner.email,
        "Renamed for the programme",
    )
    assert requested["changes"] == [
        {
            "field": "session.session_label",
            "label": f"Session “{_label(db, booking)}”: name",
            "old": old_label,
            "new": "Opening",
            "kind": "text",
        }
    ]
    [decided] = of(body, "change_decided")
    assert (decided["actor_email"], decided["outcome"], decided["reason"]) == (
        coordinator.email,
        "approved",
        "Reviewed",
    )
    assert decided["changes"] == []
    assert {requested["source_id"], decided["source_id"]} == {str(change_id)}
    [back] = of(body, "returned_to_planning")
    assert back["related_entry_ids"] == [decided["id"]]


@pytest.mark.story("SCRUM-120")
async def test_a_rejected_request_shows_the_coordinators_note(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, booking, coordinator = _confirmed(db, make_user)
    change_id = _session_change(db, event, booking)
    change_service.decide(
        db, event.id, change_id, coordinator.id, Decision.REJECT, "Programme is printed", _NOW
    )

    body = await history(make_client, coordinator, event)

    [decided] = of(body, "change_decided")
    assert (decided["outcome"], decided["reason"]) == ("rejected", "Programme is printed")
    assert of(body, "returned_to_planning") == []


@pytest.mark.story("SCRUM-120")
async def test_a_date_change_keeps_utc_values_marked_as_datetime(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator = _confirmed(db, make_user)
    assert event.end_at is not None
    _longer(db, event)

    body = await history(make_client, coordinator, event)

    [requested] = of(body, "change_requested")
    [change] = requested["changes"]
    assert (change["field"], change["label"], change["kind"]) == (
        "event.end_at",
        "End date and time",
        "datetime",
    )
    assert change["old"] == event.end_at.isoformat()
    assert change["new"] == (event.end_at + timedelta(hours=1)).isoformat()
    # Pending: no decision yet.
    assert of(body, "change_decided") == []


# ------------------------------------------------------------- AC5 completion


def completed(
    db: Session, make_user: MakeUser, with_change: bool = False
) -> tuple[EventRequest, User]:
    """Completed at its end with 40 attending, then corrected to 42 an hour later.
    `with_change` first leaves a change request pending, so both kinds of entry exist."""
    event, _, coordinator = _confirmed(db, make_user)
    assert event.end_at is not None
    if with_change:
        _longer(db, event)
    event_completions.complete(db, event.id, coordinator.id, 40, "Ran late", event.end_at)
    event_completions.correct(
        db, event.id, coordinator.id, 42, "Ran late", event.end_at + timedelta(hours=1)
    )
    return event, coordinator


@pytest.mark.story("SCRUM-120")
async def test_completion_and_its_correction_show_the_closure_values(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, coordinator = completed(db, make_user)

    body = await history(make_client, owner_of(db, event), event)

    [done] = of(body, "event_completed")
    assert done["actor_email"] == coordinator.email
    assert [(c["field"], c["old"], c["new"]) for c in done["changes"]] == [
        ("actual_attendance", None, "40"),
        ("notes", None, "Ran late"),
    ]
    [corrected] = of(body, "closure_corrected")
    assert corrected["source_type"] == "event_closure_note"
    assert [(c["field"], c["old"], c["new"]) for c in corrected["changes"]] == [
        ("actual_attendance", "40", "42"),
        ("notes", "Ran late", "Ran late"),
    ]
    assert body.index(done) < body.index(corrected)


# ------------------------------------------------------- AC7 access, privacy, no writes


@pytest.mark.story("SCRUM-120")
async def test_owner_assignee_and_lead_see_the_same_change_and_completion_entries(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """ADR-0068: the Lead sees change requests here, as the owner and assignee do."""
    event, booking, coordinator = _confirmed(db, make_user)
    _decide(db, event, _session_change(db, event, booking), coordinator, Decision.APPROVE)

    bodies: list[Any] = [
        await history(make_client, viewer, event)
        for viewer in (owner_of(db, event), coordinator, make_user("coordinator_lead"))
    ]

    assert {e["action"] for e in bodies[0]} >= {"change_requested", "change_decided"}
    # SCRUM-120 PR 3: the owner does not see safety decisions (ADR-0069); all else is equal.
    owner, assignee, lead = bodies
    assert of(owner, "safety_decided") == []
    assert assignee == lead
    assert owner == [e for e in assignee if e["action"] != "safety_decided"]


@pytest.mark.story("SCRUM-120")
@pytest.mark.parametrize("caller_kind", ["coordinator", "organiser", "venue_staff"])
async def test_everyone_else_still_gets_a_bare_403(
    caller_kind: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = completed(db, make_user)

    async with make_client(make_user(caller_kind)) as client:
        response = await client.get(f"/api/event-requests/{event.id}/history")

    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}


@pytest.mark.story("SCRUM-120")
async def test_reading_change_and_completion_entries_issues_only_selects(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, coordinator = completed(db, make_user, with_change=True)
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
