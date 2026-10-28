"""SCRUM-119: venue change entries, read through GET /event-requests/{id}/history.

The changes are made through the real writers (SCRUM-109 cancel, SCRUM-133 adopt,
SCRUM-121 expiry update), so each entry is read from exactly what those write. A buffer
change is inserted as its row, because making a booking problematic through a real venue
edit needs a second clashing booking and proves nothing more about the reader. Access is
the SCRUM-88 route's, unchanged (ADR-0062).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from domain.venue_booking import BookingStatus
from models.event_request import EventRequest
from models.user import User
from models.venue_booking import VenueBooking
from models.venue_buffer_change import VenueBufferChange
from services import event_requests as request_service
from services import venue_bookings as booking_service
from services import venue_replacements
from tests.integration.test_submit_event_request import MakeClient, MakeUser, make_draft
from tests.integration.test_venue_search import make_venue

REASON = "Speaker withdrew"


@dataclass
class Planning:
    """An Approved event in planning, its people, and two held arrangements."""

    owner: User
    coordinator: User
    lead: User
    staff: User
    event: EventRequest
    first: VenueBooking
    second: VenueBooking


def _held(
    db: Session, event: EventRequest, coordinator: User, staff: User, **fields: Any
) -> VenueBooking:
    """A tentative hold on its own new venue, so no two holds can clash."""
    assert event.start_at is not None
    now = datetime.now(UTC)
    start, end = event.start_at, event.start_at + timedelta(hours=2)
    row = VenueBooking(
        venue_id=make_venue(db, name=f"Hall {uuid.uuid4()}").id,
        event_request_id=event.id,
        requested_by_id=coordinator.id,
        session_label="Main session",
        start_at=start,
        end_at=end,
        effective_start_at=start,
        effective_end_at=end,
        status=BookingStatus.TENTATIVE,
        created_at=now - timedelta(hours=2),
        held_by_id=staff.id,
        held_at=now - timedelta(hours=1),
        expires_at=now + timedelta(days=5),
        **fields,
    )
    db.add(row)
    db.flush()
    return row


def planning(db: Session, make_user: MakeUser) -> Planning:
    owner, coordinator = make_user("organiser"), make_user("coordinator")
    lead, staff = make_user("coordinator_lead"), make_user("venue_staff")
    event = make_draft(db, owner)
    event.status = EventStatus.SUBMITTED
    db.flush()
    request_service.assign_coordinator(db, event.id, coordinator.id, datetime.now(UTC), lead.id)
    event.status = EventStatus.APPROVED
    db.flush()
    first = _held(db, event, coordinator, staff)
    second = _held(db, event, coordinator, staff)
    return Planning(owner, coordinator, lead, staff, event, first, second)


async def history(make_client: MakeClient, viewer: User, event: EventRequest) -> Any:
    async with make_client(viewer) as client:
        response = await client.get(f"/api/event-requests/{event.id}/history")
    assert response.status_code == 200
    return response.json()


def of(body: list[dict[str, Any]], action: str) -> list[dict[str, Any]]:
    return [e for e in body if e["action"] == action]


# ---------------------------------------------------------------- AC1 cancellation


@pytest.mark.story("SCRUM-119")
async def test_a_cancelled_arrangement_shows_who_when_and_why(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    p = planning(db, make_user)
    now = datetime.now(UTC)
    booking_service.cancel_arrangement(db, p.event.id, p.first.id, p.coordinator.id, REASON, now)

    [cancelled] = of(await history(make_client, p.owner, p.event), "arrangement_cancelled")

    assert (cancelled["actor_email"], cancelled["reason"]) == (p.coordinator.email, REASON)
    assert datetime.fromisoformat(cancelled["occurred_at"]) == now
    assert (cancelled["source_type"], cancelled["source_id"]) == ("venue_booking", str(p.first.id))
    assert cancelled["session_label"] == "Main session"


@pytest.mark.story("SCRUM-119")
async def test_a_refused_cancellation_leaves_no_entry(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC8: an action that failed is never shown. The writer refuses a blank reason before
    changing the row, so the booking is still there, held, with no cancellation."""
    p = planning(db, make_user)

    with pytest.raises(booking_service.InvalidCancellationError):
        booking_service.cancel_arrangement(
            db, p.event.id, p.first.id, p.coordinator.id, "  ", datetime.now(UTC)
        )
    body = await history(make_client, p.owner, p.event)

    assert of(body, "arrangement_cancelled") == []
    first = [e["action"] for e in body if e["source_id"] == str(p.first.id)]
    assert first == ["venue_requested", "hold_created"]


# ------------------------------------------------------------------ AC3 replacement


@pytest.mark.story("SCRUM-119")
async def test_adopting_a_replacement_links_both_arrangements_both_ways(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    p = planning(db, make_user)
    p.second.replaces_booking_id = p.first.id
    db.flush()
    now = datetime.now(UTC)
    venue_replacements.adopt(db, p.event.id, p.second.id, p.coordinator.id, now)

    body = await history(make_client, p.owner, p.event)

    [requested] = [e for e in of(body, "venue_requested") if e["source_id"] == str(p.second.id)]
    assert requested["related_booking_id"] == str(p.first.id)
    linked = [
        (e["action"], e["source_id"], e["related_booking_id"])
        for e in body
        if e["action"] in ("replacement_adopted", "arrangement_cancelled")
    ]
    assert linked == [
        ("replacement_adopted", str(p.second.id), str(p.first.id)),
        ("arrangement_cancelled", str(p.first.id), str(p.second.id)),
    ]
    assert {datetime.fromisoformat(e["occurred_at"]) for e in body[-2:]} == {now}
    assert len({e["id"] for e in body}) == len(body)


# --------------------------------------------------------------- AC2 expiry update gap


@pytest.mark.story("SCRUM-119")
async def test_an_expiry_update_adds_no_entry_and_the_hold_shows_the_new_expiry(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """ADR-0064 gap, pinned: SCRUM-121 overwrites the expiry and records nothing else."""
    p = planning(db, make_user)
    before = await history(make_client, p.owner, p.event)
    new_expiry = (datetime.now(UTC) + timedelta(days=10)).replace(microsecond=0)

    booking_service.update_hold_expiry(db, p.first.id, new_expiry, datetime.now(UTC))
    after = await history(make_client, p.owner, p.event)

    assert [e["id"] for e in after] == [e["id"] for e in before]
    [hold] = [e for e in of(after, "hold_created") if e["source_id"] == str(p.first.id)]
    assert datetime.fromisoformat(hold["hold_expires_at"]) == new_expiry


# --------------------------------------------------------------- AC4 session period


@pytest.mark.story("SCRUM-119")
async def test_venue_entries_show_their_session_label_and_period(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    p = planning(db, make_user)

    venue_entries = [
        e
        for e in await history(make_client, p.owner, p.event)
        if e["source_type"] == "venue_booking"
    ]

    assert len(venue_entries) == 4
    for e in venue_entries:
        assert e["session_label"] == "Main session"
        assert datetime.fromisoformat(e["session_start_at"]) == p.first.start_at
        assert datetime.fromisoformat(e["session_end_at"]) == p.first.end_at


# ---------------------------------------------------------------- AC5 buffer change


def _buffer_change(db: Session, p: Planning, flagged: list[uuid.UUID]) -> VenueBufferChange:
    row = VenueBufferChange(
        venue_id=p.first.venue_id,
        changed_by_id=p.staff.id,
        changed_at=datetime.now(UTC),
        old_setup_minutes=0,
        old_turnaround_minutes=15,
        new_setup_minutes=45,
        new_turnaround_minutes=30,
        flagged_booking_ids=flagged,
    )
    db.add(row)
    db.flush()
    return row


@pytest.mark.story("SCRUM-119")
async def test_a_buffer_change_shows_old_and_new_buffers_and_only_this_events_booking(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    p = planning(db, make_user)
    elsewhere = uuid.uuid4()  # another event's booking caught out by the same change
    change = _buffer_change(db, p, [elsewhere, p.first.id])
    _buffer_change(db, p, [uuid.uuid4()])  # caught out nothing of this event

    body = await history(make_client, p.owner, p.event)

    [entry] = of(body, "buffer_changed")
    assert (entry["source_type"], entry["source_id"]) == ("venue_buffer_change", str(change.id))
    assert entry["actor_email"] == p.staff.email
    assert entry["affected_booking_ids"] == [str(p.first.id)]
    assert entry["changes"] == [
        # SCRUM-120 adds `kind` to every change (ADR-0068).
        {
            "field": "setup_minutes",
            "label": "Setup time (minutes)",
            "old": "0",
            "new": "45",
            "kind": "text",
        },
        {
            "field": "turnaround_minutes",
            "label": "Turnaround time (minutes)",
            "old": "15",
            "new": "30",
            "kind": "text",
        },
    ]
    assert str(elsewhere) not in str(body)


# ------------------------------------------------------- AC7 access, privacy, no writes


def _with_every_change(db: Session, make_user: MakeUser) -> Planning:
    p = planning(db, make_user)
    p.second.replaces_booking_id = p.first.id
    db.flush()
    venue_replacements.adopt(db, p.event.id, p.second.id, p.coordinator.id, datetime.now(UTC))
    _buffer_change(db, p, [p.first.id])
    return p


@pytest.mark.story("SCRUM-119")
async def test_owner_assignee_and_lead_see_the_same_new_entries(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    p = _with_every_change(db, make_user)

    bodies = [
        await history(make_client, viewer, p.event)
        for viewer in (p.owner, p.coordinator, p.lead, make_user("coordinator_lead"))
    ]

    new = {"replacement_adopted", "arrangement_cancelled", "buffer_changed"}
    assert {e["action"] for e in bodies[0]} >= new
    assert all(body == bodies[0] for body in bodies)


@pytest.mark.story("SCRUM-119")
@pytest.mark.parametrize(
    "caller_kind",
    ["unassigned_coordinator", "peer_organiser", "venue_staff", "tech_support", "attendee"],
)
async def test_everyone_else_still_gets_a_bare_403(
    caller_kind: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    p = _with_every_change(db, make_user)
    callers = {
        "unassigned_coordinator": lambda: make_user("coordinator"),
        "peer_organiser": lambda: make_user("organiser", organisation_id=p.owner.organisation_id),
    }
    caller = callers.get(caller_kind, lambda: make_user(caller_kind))()

    async with make_client(caller) as client:
        response = await client.get(f"/api/event-requests/{p.event.id}/history")

    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}


@pytest.mark.story("SCRUM-119")
async def test_reading_the_new_entries_issues_only_selects(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    p = _with_every_change(db, make_user)
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
        for viewer in (p.owner, p.coordinator, p.lead):
            await history(make_client, viewer, p.event)
    finally:
        sa_event.remove(connection, "before_cursor_execute", capture)
        sa_event.remove(db, "before_flush", count_flush)

    assert statements
    assert all(s.lstrip().upper().startswith("SELECT") for s in statements)
    assert flushes == []
