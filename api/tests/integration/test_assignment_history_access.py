"""SCRUM-105: the owning Organiser and the current Coordinator read assignment history.

Access is `require_event_access(READ_ASSIGNMENT_HISTORY)` (ADR-0047): any Lead, the
owning Organiser, or the Coordinator currently on the request. Everyone else gets a 403
that discloses nothing, reassignment moves access at once, and reading never writes.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from models.event_request import EventRequest
from models.user import User
from repositories import coordinator_assignments as history_repo
from services import event_requests as service
from tests.integration.test_submit_event_request import MakeClient, MakeUser, make_draft

FIRST_AT = datetime(2026, 4, 2, 9, 0, tzinfo=UTC)


def submitted(db: Session, owner: User) -> EventRequest:
    """A Submitted, never-assigned request, arranged directly as SCRUM-97's tests do."""
    request = make_draft(db, owner)
    request.status = EventStatus.SUBMITTED
    request.submitted_at = FIRST_AT - timedelta(days=1)
    db.flush()
    return request


def assign(db: Session, request: EventRequest, coordinator: User, lead: User) -> None:
    """The first assignment, through the real service, so it records a history row."""
    service.assign_coordinator(db, request.id, coordinator.id, FIRST_AT, lead.id)


def reassign(
    db: Session, request: EventRequest, to: User, current: User, lead: User, hours: int
) -> None:
    """A reassignment `hours` after the first assignment, through the real service."""
    service.reassign_coordinator(
        db, request.id, to.id, current.id, lead.id, FIRST_AT + timedelta(hours=hours)
    )


def url(request: EventRequest) -> str:
    return f"/api/event-requests/{request.id}/assignment-history"


@pytest.mark.story("SCRUM-105")
async def test_owner_reads_the_history_oldest_first_with_emails(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1: previous Coordinator (none on the first entry), new Coordinator, acting Lead
    and time, oldest first, across A→B→C."""
    owner = make_user("organiser")
    a, b, c = (make_user("coordinator") for _ in range(3))
    lead = make_user("coordinator_lead")
    request = submitted(db, owner)
    assign(db, request, a, lead)
    reassign(db, request, b, a, lead, hours=1)
    reassign(db, request, c, b, lead, hours=2)

    async with make_client(owner) as client:
        response = await client.get(url(request))

    assert response.status_code == 200
    entries = response.json()
    assert [
        (e["previous_coordinator_email"], e["new_coordinator_email"], e["acted_by_email"])
        for e in entries
    ] == [
        (None, a.email, lead.email),
        (a.email, b.email, lead.email),
        (b.email, c.email, lead.email),
    ]
    assert [e["previous_coordinator_id"] for e in entries] == [None, str(a.id), str(b.id)]
    assert [datetime.fromisoformat(e["assigned_at"]) for e in entries] == [
        FIRST_AT,
        FIRST_AT + timedelta(hours=1),
        FIRST_AT + timedelta(hours=2),
    ]


@pytest.mark.story("SCRUM-105")
async def test_current_coordinator_and_lead_read_the_same_history_as_the_owner(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC2, AC3: the assigned Coordinator and a Lead get exactly the owner's body."""
    owner = make_user("organiser")
    a, b = make_user("coordinator"), make_user("coordinator")
    lead = make_user("coordinator_lead")
    request = submitted(db, owner)
    assign(db, request, a, lead)
    reassign(db, request, b, a, lead, hours=1)

    bodies = []
    for viewer in (owner, b, lead, make_user("coordinator_lead")):
        async with make_client(viewer) as client:
            response = await client.get(url(request))
        assert response.status_code == 200
        bodies.append(response.json())

    assert len(bodies[0]) == 2
    assert all(body == bodies[0] for body in bodies)


@pytest.mark.story("SCRUM-105")
async def test_lead_access_is_unchanged_for_a_draft(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC3: a Lead still reads a draft's (empty) history; VIEW would have refused it."""
    draft = make_draft(db, make_user("organiser"))

    async with make_client(make_user("coordinator_lead")) as client:
        response = await client.get(url(draft))

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.story("SCRUM-105")
@pytest.mark.parametrize(
    "caller_kind",
    [
        "peer_organiser",
        "unrelated_organiser",
        "unassigned_coordinator",
        "venue_staff",
        "tech_support",
        "attendee",
    ],
)
async def test_everyone_else_gets_403_without_disclosure_or_mutation(
    caller_kind: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC4, AC7: a bare 403 with no history in it, and the trail is untouched."""
    owner = make_user("organiser")
    a = make_user("coordinator")
    lead = make_user("coordinator_lead")
    request = submitted(db, owner)
    assign(db, request, a, lead)
    callers = {
        "peer_organiser": lambda: make_user("organiser", organisation_id=owner.organisation_id),
        "unrelated_organiser": lambda: make_user("organiser"),
        "unassigned_coordinator": lambda: make_user("coordinator"),
    }
    caller = callers.get(caller_kind, lambda: make_user(caller_kind))()

    async with make_client(caller) as client:
        response = await client.get(url(request))

    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}
    db.refresh(request)
    assert request.coordinator_id == a.id
    assert history_repo.count_for_event(db, request.id) == 1


@pytest.mark.story("SCRUM-105")
async def test_reassignment_moves_access_from_outgoing_to_incoming_coordinator(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC5: the outgoing Coordinator loses access at once and the incoming one gains it."""
    owner = make_user("organiser")
    a, b = make_user("coordinator"), make_user("coordinator")
    lead = make_user("coordinator_lead")
    request = submitted(db, owner)
    assign(db, request, a, lead)

    async with make_client(a) as client:
        assert (await client.get(url(request))).status_code == 200
    async with make_client(b) as client:
        assert (await client.get(url(request))).status_code == 403

    reassign(db, request, b, a, lead, hours=1)

    async with make_client(a) as client:
        outgoing = await client.get(url(request))
    async with make_client(b) as client:
        incoming = await client.get(url(request))
    assert outgoing.status_code == 403
    assert outgoing.json() == {"detail": "Forbidden"}
    assert incoming.status_code == 200
    assert len(incoming.json()) == 2


@pytest.mark.story("SCRUM-105")
@pytest.mark.parametrize("other_role", ["owner", "coordinator_lead"])
async def test_outgoing_coordinator_keeps_access_through_another_qualifying_role(
    other_role: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC5: losing the assignment does not remove access held as the owner or a Lead."""
    if other_role == "owner":
        dual = make_user("organiser", "coordinator")
        owner = dual
    else:
        dual = make_user("coordinator", "coordinator_lead")
        owner = make_user("organiser")
    b = make_user("coordinator")
    lead = make_user("coordinator_lead")
    request = submitted(db, owner)
    assign(db, request, dual, lead)
    reassign(db, request, b, dual, lead, hours=1)

    async with make_client(dual) as client:
        response = await client.get(url(request))

    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.story("SCRUM-105")
async def test_never_assigned_event_returns_an_empty_history(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC6: the owner of a submitted, unassigned event gets [] — the UI's empty state."""
    owner = make_user("organiser")
    request = submitted(db, owner)

    async with make_client(owner) as client:
        response = await client.get(url(request))

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.story("SCRUM-105")
async def test_reading_writes_nothing_and_grants_no_assign_or_reassign(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC7: the owner and the assigned Coordinator read repeatedly, nothing changes, and
    both are still refused the Lead's assign and reassign actions."""
    owner = make_user("organiser")
    a, b = make_user("coordinator"), make_user("coordinator")
    lead = make_user("coordinator_lead")
    request = submitted(db, owner)
    assign(db, request, a, lead)
    other = submitted(db, owner)
    before = [entry.id for entry in history_repo.list_for_event(db, request.id)]

    for viewer in (owner, a):
        async with make_client(viewer) as client:
            for _ in range(2):
                assert (await client.get(url(request))).status_code == 200
            reassigned = await client.post(
                f"/api/event-requests/{request.id}/reassign",
                json={
                    "coordinator_id": str(b.id),
                    "expected_current_coordinator_id": str(a.id),
                },
            )
            assigned = await client.post(
                f"/api/event-requests/{other.id}/assign", json={"coordinator_id": str(b.id)}
            )
        assert reassigned.status_code == 403
        assert assigned.status_code == 403

    db.refresh(request)
    db.refresh(other)
    assert request.coordinator_id == a.id
    assert other.coordinator_id is None
    assert [entry.id for entry in history_repo.list_for_event(db, request.id)] == before
    assert history_repo.count_for_event(db, other.id) == 0


@pytest.mark.story("SCRUM-105")
async def test_missing_request_is_404_for_a_non_lead(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    """ADR-0047 trade-off: the shared dependency loads the request first, so a missing id
    is 404 for anyone signed in, as on every other per-event route."""
    async with make_client(make_user("organiser")) as client:
        response = await client.get(
            "/api/event-requests/00000000-0000-0000-0000-000000000000/assignment-history"
        )

    assert response.status_code == 404
