"""SCRUM-120: safety decisions and venue closures, read through
GET /event-requests/{id}/history.

Decisions are recorded by SCRUM-79's writer and closures saved by SCRUM-81/132's. Safety
decision entries are shown only to a viewer `may_read_safety_reviews` allows, the same rule
as GET /safety-reviews/{id}/history, so the owner never sees one (ADR-0069).
"""

import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy.orm import Session

from domain.roles import Role
from domain.safety_review import SafetyDecision, fingerprint
from models.event_request import EventRequest
from models.user import User
from models.venue import Venue
from models.venue_booking import VenueBooking
from models.venue_closure_impact import VenueClosureImpact
from services import event_requests as request_service
from services import safety_reviews as safety_service
from tests.integration.test_closure_replanning import _close
from tests.integration.test_event_history_lifecycle import history, of, owner_of
from tests.integration.test_safety_approval_invalidation import _confirmed
from tests.integration.test_safety_review import _NOW, arranged_event
from tests.integration.test_submit_event_request import MakeClient, MakeUser

_MINUTE = timedelta(minutes=1)


def decided(db: Session, make_user: MakeUser) -> tuple[EventRequest, VenueBooking, User, User]:
    """An event in planning with all three kinds of decision, a minute apart."""
    event, booking, coordinator = arranged_event(db, make_user)
    officer = make_user(Role.SAFETY_OFFICER.value)
    for offset, (made, comment) in enumerate(
        [
            (SafetyDecision.REQUEST_CHANGES, "Add a second exit sign"),
            (SafetyDecision.REJECT, "Capacity over the fire limit"),
            (SafetyDecision.APPROVE, "Egress is clear"),
        ]
    ):
        at = _NOW + offset * _MINUTE
        plan = safety_service.plan_of(db, event, at)
        safety_service.record(db, event, made, comment, fingerprint(plan), officer.id, at)
    return event, booking, coordinator, officer


# ------------------------------------------------------------ AC2 safety decisions


@pytest.mark.story("SCRUM-120")
async def test_each_safety_decision_shows_the_officer_outcome_and_comment(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator, officer = decided(db, make_user)

    rows = of(await history(make_client, coordinator, event), "safety_decided")

    assert [(e["actor_email"], e["outcome"], e["reason"]) for e in rows] == [
        (officer.email, "changes_requested", "Add a second exit sign"),
        (officer.email, "rejected", "Capacity over the fire limit"),
        (officer.email, "approved", "Egress is clear"),
    ]
    assert {e["source_type"] for e in rows} == {"safety_review"}


@pytest.mark.story("SCRUM-120")
async def test_the_owner_gets_no_trace_of_a_safety_decision(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """ADR-0069: no entry, no comment and no decision id, as ADR-0036 does for notes."""
    event, _, coordinator, _ = decided(db, make_user)

    owners = await history(make_client, owner_of(db, event), event)
    assignees = await history(make_client, coordinator, event)

    assert of(owners, "safety_decided") == []
    assert "exit sign" not in str(owners)
    for decision in of(assignees, "safety_decided"):
        assert decision["source_id"] not in str(owners)
    assert owners == [e for e in assignees if e["action"] != "safety_decided"]


@pytest.mark.story("SCRUM-120")
@pytest.mark.parametrize(
    "viewer",
    [
        "owner",
        "assignee",
        "lead",
        "owner_who_is_also_a_safety_officer",
        "lead_who_is_also_the_assignee",
        "outgoing_coordinator",
        "unassigned_coordinator",
        "safety_officer",
        "venue_staff",
    ],
)
async def test_safety_entries_match_what_get_safety_reviews_allows(
    viewer: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """The history never shows more or fewer decisions than the safety-reviews route does
    to anyone who may read the history. Who may read the history is unchanged."""
    event, _, coordinator, _ = decided(db, make_user)
    lead = make_user("coordinator_lead")
    if viewer == "owner_who_is_also_a_safety_officer":
        event.organiser_id = make_user("organiser", Role.SAFETY_OFFICER.value).id
    if viewer == "lead_who_is_also_the_assignee":
        event.coordinator_id = make_user("coordinator", "coordinator_lead").id
    db.flush()
    callers: dict[str, Callable[[], User | None]] = {
        "owner": lambda: owner_of(db, event),
        "assignee": lambda: coordinator,
        "lead": lambda: lead,
        "owner_who_is_also_a_safety_officer": lambda: owner_of(db, event),
        "lead_who_is_also_the_assignee": lambda: db.get(User, event.coordinator_id),
        "outgoing_coordinator": lambda: coordinator,
        "unassigned_coordinator": lambda: make_user("coordinator"),
        "safety_officer": lambda: make_user(Role.SAFETY_OFFICER.value),
        "venue_staff": lambda: make_user("venue_staff"),
    }
    caller = callers[viewer]()
    assert caller is not None
    if viewer == "outgoing_coordinator":
        request_service.reassign_coordinator(
            db, event.id, make_user("coordinator").id, coordinator.id, lead.id, _NOW
        )

    async with make_client(caller) as client:
        entries = await client.get(f"/api/event-requests/{event.id}/history")
        decisions = await client.get(f"/api/safety-reviews/{event.id}/history")

    allowed = [d["id"] for d in decisions.json()] if decisions.status_code == 200 else []
    if entries.status_code != 200:
        # Outside the history's audience, which SCRUM-120 does not widen.
        assert entries.status_code == 403
        return
    in_history = [e["source_id"] for e in entries.json() if e["action"] == "safety_decided"]
    assert in_history == allowed


# ----------------------------------------------------------------- AC4 closures


@pytest.mark.story("SCRUM-120")
async def test_a_closure_shows_the_period_reason_and_only_this_events_arrangement(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, booking, _ = arranged_event(db, make_user)
    staff = make_user("venue_staff")
    closure = _close(db, booking, staff)
    venue = db.get(Venue, booking.venue_id)
    assert venue is not None
    # Another event's arrangement in the same snapshot must not reach this history.
    [row] = db.query(VenueClosureImpact).filter_by(unavailability_id=closure.id).all()
    elsewhere = uuid.uuid4()
    row.affected_booking_ids = [*row.affected_booking_ids, elsewhere]
    db.flush()

    body = await history(make_client, owner_of(db, event), event)

    [entry] = of(body, "venue_closed")
    assert (entry["actor_email"], entry["reason"], entry["venue_name"]) == (
        staff.email,
        "Burst pipe",
        venue.name,
    )
    assert entry["period_start_at"][:19] == booking.start_at.isoformat()[:19]
    assert entry["period_end_at"][:19] == booking.end_at.isoformat()[:19]
    assert entry["affected_booking_ids"] == [str(booking.id)]
    assert str(elsewhere) not in str(body)
    # An event in planning does not go back to planning.
    assert of(body, "returned_to_planning") == []


@pytest.mark.story("SCRUM-120")
async def test_a_closure_return_links_its_closure_entry(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, booking, coordinator = _confirmed(db, make_user)
    staff = make_user("venue_staff")
    _close(db, booking, staff)

    body = await history(make_client, coordinator, event)

    [closed] = of(body, "venue_closed")
    [back] = of(body, "returned_to_planning")
    assert (back["actor_email"], back["replan_cause"]) == (staff.email, "venue_closure")
    assert back["related_entry_ids"] == [closed["id"]]


# ------------------------------------------------------- AC7 access, privacy, no writes


@pytest.mark.story("SCRUM-120")
async def test_assignee_and_lead_see_the_same_safety_and_closure_entries(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, booking, coordinator, _ = decided(db, make_user)
    _close(db, booking, make_user("venue_staff"), at=_NOW + 5 * _MINUTE)

    bodies: list[Any] = [
        await history(make_client, viewer, event)
        for viewer in (coordinator, make_user("coordinator_lead"))
    ]

    assert {e["action"] for e in bodies[0]} >= {"safety_decided", "venue_closed"}
    assert bodies[0] == bodies[1]


@pytest.mark.story("SCRUM-120")
async def test_reading_safety_and_closure_entries_issues_only_selects(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, booking, coordinator, _ = decided(db, make_user)
    _close(db, booking, make_user("venue_staff"), at=_NOW + 5 * _MINUTE)
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
