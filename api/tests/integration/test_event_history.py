"""SCRUM-88: one event's history, read from the records earlier stories keep.

Access is `require_event_access(READ_EVENT_HISTORY)` (ADR-0062): any Lead, the owning
Organiser or the current assigned Coordinator. Clarification notes follow SCRUM-106 through
`may_read_clarifications`, the same rule as GET /clarifications. Reading never writes.

The event's records are arranged directly, as SCRUM-105's tests do, except where a real
writer is cheap to call: the Lead's assignment, the note and the hold expiry sweep.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy.orm import Session

from domain.event_clarification import ClarificationKind
from domain.event_status import EventStatus
from domain.venue_booking import BookingStatus
from models.event_clarification import EventClarification
from models.event_request import EventRequest
from models.user import User
from models.venue import Venue
from models.venue_booking import VenueBooking
from repositories import event_history as history_repo
from services import event_clarifications as clarification_service
from services import event_requests as request_service
from services.venue_hold_expiry import expire_due_holds
from tests.integration.test_submit_event_request import MakeClient, MakeUser, make_draft
from tests.integration.test_venue_search import make_venue

NOTE_TEXT = "Internal: the organiser's budget looks unrealistic"


@dataclass
class Recorded:
    """An event with one record of every kind SCRUM-88 reads, and the people on it."""

    owner: User
    coordinator: User
    lead: User
    staff: User
    event: EventRequest
    note: EventClarification
    rejected: VenueBooking
    confirmed: VenueBooking
    expired: VenueBooking


def _booking(
    db: Session, event: EventRequest, venue: Venue, requester: User, at: datetime, **fields: Any
) -> VenueBooking:
    assert event.start_at is not None
    start, end = event.start_at, event.start_at + timedelta(hours=2)
    row = VenueBooking(
        venue_id=venue.id,
        event_request_id=event.id,
        requested_by_id=requester.id,
        session_label="Main session",
        start_at=start,
        end_at=end,
        effective_start_at=start,
        effective_end_at=end,
        created_at=at,
        **fields,
    )
    db.add(row)
    db.flush()
    return row


def record(db: Session, make_user: MakeUser) -> Recorded:
    """Created, submitted, assigned, noted, approved and confirmed once, with a rejected,
    a confirmed and an expired venue request. All three requests share one creation
    time, so their order comes from the tie-breaker."""
    owner, coordinator = make_user("organiser"), make_user("coordinator")
    lead, staff = make_user("coordinator_lead"), make_user("venue_staff")
    base = datetime.now(UTC).replace(microsecond=0) - timedelta(days=10)

    def at(hours: float) -> datetime:
        return base + timedelta(hours=hours)

    event = make_draft(db, owner)
    event.created_at = at(0)
    event.status = EventStatus.SUBMITTED
    event.submitted_at = at(1)
    db.flush()
    request_service.assign_coordinator(db, event.id, coordinator.id, at(2), lead.id)
    note = clarification_service.create_message(
        db, event.id, coordinator.id, ClarificationKind.REQUEST, NOTE_TEXT, at(2.5)
    )
    event.status = EventStatus.APPROVED
    event.decided_by_id, event.decided_at = coordinator.id, at(3)
    # Confirmed once and since replanned, so it is Approved with a confirmation on record.
    event.confirmed_by_id, event.confirmed_at = coordinator.id, at(8)

    venue = make_venue(db, name=f"History Hall {event.id}")
    rejected = _booking(
        db,
        event,
        venue,
        coordinator,
        at(4),
        status=BookingStatus.REJECTED,
        decided_by_id=staff.id,
        decided_at=at(5),
        decision_reason="Closed for works",
    )
    confirmed = _booking(
        db,
        event,
        venue,
        coordinator,
        at(4),
        status=BookingStatus.CONFIRMED,
        held_by_id=staff.id,
        held_at=at(5),
        expires_at=at(48),
    )
    expired = _booking(
        db,
        event,
        make_venue(db, name=f"Annex {event.id}"),
        coordinator,
        at(4),
        status=BookingStatus.TENTATIVE,
        held_by_id=staff.id,
        held_at=at(5),
        expires_at=at(6),
    )
    expire_due_holds(db, at(7))
    db.refresh(event)
    return Recorded(owner, coordinator, lead, staff, event, note, rejected, confirmed, expired)


def url(event: EventRequest) -> str:
    return f"/api/event-requests/{event.id}/history"


def keys(body: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [(e["action"], e["source_id"]) for e in body]


# ------------------------------------------------------------------- AC1-AC4 content


@pytest.mark.story("SCRUM-88")
async def test_assignee_sees_every_recorded_action_once_oldest_first(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    r = record(db, make_user)
    tied = sorted([r.rejected, r.confirmed, r.expired], key=lambda b: str(b.id))
    event_id = str(r.event.id)

    async with make_client(r.coordinator) as client:
        response = await client.get(url(r.event))

    assert response.status_code == 200
    body = response.json()
    assert keys(body) == [
        ("draft_created", event_id),
        ("submitted", event_id),
        ("coordinator_assigned", keys(body)[2][1]),
        ("clarification_requested", str(r.note.id)),
        ("review_decided", event_id),
        *[("venue_requested", str(b.id)) for b in tied],
        ("venue_decided", str(r.rejected.id)),
        *[("hold_created", str(b.id)) for b in tied if b is not r.rejected],
        ("hold_expired", str(r.expired.id)),
        ("hold_confirmed", str(r.confirmed.id)),
    ]
    assert len({e["id"] for e in body}) == len(body)


@pytest.mark.story("SCRUM-88")
async def test_each_entry_carries_actor_time_source_and_outcome(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC2: who, when (UTC), which record, and the outcome or reason where recorded."""
    r = record(db, make_user)

    async with make_client(r.owner) as client:
        body = (await client.get(url(r.event))).json()
    by_action = {e["action"]: e for e in body if e["action"] != "venue_requested"}

    assert by_action["submitted"]["actor_email"] == r.owner.email
    assert datetime.fromisoformat(by_action["submitted"]["occurred_at"]) == r.event.submitted_at
    assert by_action["coordinator_assigned"]["actor_email"] == r.lead.email
    assert by_action["coordinator_assigned"]["new_coordinator_email"] == r.coordinator.email
    decided = by_action["review_decided"]
    assert (decided["actor_email"], decided["outcome"], decided["reason"]) == (
        r.coordinator.email,
        "approved",
        None,
    )
    venue = by_action["venue_decided"]
    assert (venue["actor_email"], venue["outcome"], venue["reason"]) == (
        r.staff.email,
        "rejected",
        "Closed for works",
    )
    assert (venue["source_type"], venue["source_id"]) == ("venue_booking", str(r.rejected.id))
    expired = by_action["hold_expired"]
    assert (expired["actor_id"], expired["actor_email"]) == (None, None)
    assert datetime.fromisoformat(expired["occurred_at"]) == r.expired.expires_at
    confirmed = by_action["hold_confirmed"]
    assert confirmed["actor_email"] == r.coordinator.email
    assert datetime.fromisoformat(confirmed["occurred_at"]) == r.event.confirmed_at


# --------------------------------------------------------------------- AC6 access


@pytest.mark.story("SCRUM-88")
@pytest.mark.parametrize("viewer", ["owner", "coordinator", "lead"])
async def test_owner_assignee_and_any_lead_may_read(
    viewer: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    r = record(db, make_user)
    caller = make_user("coordinator_lead") if viewer == "lead" else getattr(r, viewer)

    async with make_client(caller) as client:
        response = await client.get(url(r.event))

    assert response.status_code == 200
    assert len(response.json()) >= 12


@pytest.mark.story("SCRUM-88")
async def test_a_lead_reads_a_drafts_creation(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    draft = make_draft(db, make_user("organiser"))

    async with make_client(make_user("coordinator_lead")) as client:
        response = await client.get(url(draft))

    assert response.status_code == 200
    assert [e["action"] for e in response.json()] == ["draft_created"]


@pytest.mark.story("SCRUM-88")
@pytest.mark.parametrize(
    "caller_kind",
    [
        "outgoing_coordinator",
        "unassigned_coordinator",
        "peer_organiser",
        "unrelated_organiser",
        "venue_staff",
        "tech_support",
        "attendee",
    ],
)
async def test_everyone_else_gets_a_bare_403(
    caller_kind: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    r = record(db, make_user)
    if caller_kind == "outgoing_coordinator":
        caller = r.coordinator
        request_service.reassign_coordinator(
            db,
            r.event.id,
            make_user("coordinator").id,
            r.coordinator.id,
            r.lead.id,
            datetime.now(UTC),
        )
    elif caller_kind == "peer_organiser":
        caller = make_user("organiser", organisation_id=r.owner.organisation_id)
    else:
        role = {"unassigned_coordinator": "coordinator", "unrelated_organiser": "organiser"}
        caller = make_user(role.get(caller_kind, caller_kind))

    async with make_client(caller) as client:
        response = await client.get(url(r.event))

    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}


@pytest.mark.story("SCRUM-88")
async def test_unauthenticated_is_401_and_a_missing_event_404(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    draft = make_draft(db, make_user("organiser"))

    async with make_client(None) as client:
        unauthenticated = await client.get(url(draft))
    async with make_client(make_user("coordinator_lead")) as client:
        missing = await client.get(
            "/api/event-requests/00000000-0000-0000-0000-000000000000/history"
        )

    assert unauthenticated.status_code == 401
    assert missing.status_code == 404


# ------------------------------------------------------------------- AC7 privacy


@pytest.mark.story("SCRUM-88")
@pytest.mark.parametrize("viewer", ["owner", "lead"])
async def test_a_viewer_who_may_not_read_notes_gets_no_trace_of_them(
    viewer: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """SCRUM-106: not the text, not the entry, not the note's id (ADR-0036)."""
    r = record(db, make_user)
    caller = r.lead if viewer == "lead" else r.owner

    async with make_client(caller) as client:
        response = await client.get(url(r.event))

    assert response.status_code == 200
    assert NOTE_TEXT not in response.text
    assert str(r.note.id) not in response.text
    assert all(e["source_type"] != "clarification" for e in response.json())
    assert all(e["note"] is None for e in response.json())


@pytest.mark.story("SCRUM-88")
async def test_reassignment_moves_note_entries_to_the_incoming_coordinator(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    r = record(db, make_user)
    incoming = make_user("coordinator")
    request_service.reassign_coordinator(
        db, r.event.id, incoming.id, r.coordinator.id, r.lead.id, datetime.now(UTC)
    )

    async with make_client(incoming) as client:
        body = (await client.get(url(r.event))).json()

    [note] = [e for e in body if e["source_type"] == "clarification"]
    assert (note["note"], note["actor_email"]) == (NOTE_TEXT, r.coordinator.email)
    assert body[-1]["action"] == "coordinator_reassigned"


@pytest.mark.story("SCRUM-88")
@pytest.mark.parametrize(
    "viewer",
    [
        "owner",
        "assignee",
        "lead",
        "lead_who_is_also_an_unassigned_coordinator",
        "owner_who_is_also_the_assignee",
        "lead_who_is_also_the_assignee",
        "outgoing_coordinator",
        "unassigned_coordinator",
        "peer_organiser",
        "venue_staff",
    ],
)
async def test_note_entries_match_what_get_clarifications_allows(
    viewer: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """The history never shows more or fewer notes than the clarifications route does."""
    owner = (
        make_user("organiser", "coordinator")
        if viewer.startswith("owner_who")
        else (make_user("organiser"))
    )
    lead = make_user("coordinator_lead")
    assignee = {
        "owner_who_is_also_the_assignee": owner,
        "lead_who_is_also_the_assignee": make_user("coordinator", "coordinator_lead"),
    }.get(viewer) or make_user("coordinator")
    event = make_draft(db, owner)
    event.status = EventStatus.SUBMITTED
    db.flush()
    request_service.assign_coordinator(db, event.id, assignee.id, datetime.now(UTC), lead.id)
    note = clarification_service.create_message(
        db, event.id, assignee.id, ClarificationKind.REQUEST, NOTE_TEXT, datetime.now(UTC)
    )
    caller = {
        "owner": owner,
        "assignee": assignee,
        "lead": lead,
        "lead_who_is_also_an_unassigned_coordinator": make_user("coordinator", "coordinator_lead"),
        "owner_who_is_also_the_assignee": owner,
        "lead_who_is_also_the_assignee": assignee,
        "outgoing_coordinator": assignee,
        "unassigned_coordinator": make_user("coordinator"),
        "peer_organiser": make_user("organiser", organisation_id=owner.organisation_id),
        "venue_staff": make_user("venue_staff"),
    }[viewer]
    if viewer == "outgoing_coordinator":
        request_service.reassign_coordinator(
            db, event.id, make_user("coordinator").id, assignee.id, lead.id, datetime.now(UTC)
        )

    async with make_client(caller) as client:
        history = await client.get(url(event))
        notes = await client.get(f"/api/event-requests/{event.id}/clarifications")

    in_history = (
        [e["source_id"] for e in history.json() if e["source_type"] == "clarification"]
        if history.status_code == 200
        else []
    )
    allowed = [n["id"] for n in notes.json()] if notes.status_code == 200 else []
    assert in_history == allowed
    assert (notes.status_code == 200) == (in_history == [str(note.id)])


# ------------------------------------------------------------ AC5 reading writes nothing


@pytest.mark.story("SCRUM-88")
async def test_opening_and_refreshing_issue_only_selects_and_change_no_record(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    r = record(db, make_user)

    def snapshot() -> tuple[object, ...]:
        db.expire_all()
        return (
            history_repo.request_record(db, r.event.id),
            history_repo.assignment_records(db, r.event.id),
            history_repo.clarification_records(db, r.event.id),
            sorted(history_repo.booking_records(db, r.event.id), key=lambda b: str(b.id)),
            r.event.updated_at,
        )

    before = snapshot()
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
        for viewer in (r.owner, r.coordinator, r.lead):
            async with make_client(viewer) as client:
                for _ in range(2):
                    assert (await client.get(url(r.event))).status_code == 200
    finally:
        sa_event.remove(connection, "before_cursor_execute", capture)
        sa_event.remove(db, "before_flush", count_flush)

    assert statements, "the listener saw the reads"
    assert all(s.lstrip().upper().startswith("SELECT") for s in statements)
    assert flushes == []
    assert snapshot() == before
