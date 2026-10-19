"""SCRUM-112: a peer Organiser gets the organisation calendar's fields and nothing else.

Same-organisation membership no longer grants VIEW (ADR-0039). The owner keeps full
access, a staff role on the same account keeps that role's access, and no refused
request changes anything.
"""

import uuid
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from models.event_clarification import EventClarification
from models.event_coordinator_assignment import EventCoordinatorAssignment
from models.event_equipment_requirement import EventEquipmentRequirement
from models.event_request import EventRequest
from models.user import User
from models.venue_booking import VenueBooking
from tests.integration.test_submit_event_request import MakeClient, MakeUser, make_draft

_ANY_ID = uuid.uuid4()

# Every per-event route an Organiser could try, read or write. Bodies are minimal: the
# access check runs before body validation, so a 403 here is the refusal, not a 422.
PEER_ROUTES = [
    ("GET", "", None),
    ("PATCH", "", {"name": "Changed by a peer"}),
    ("PATCH", "/planning-info", {"name": "Changed by a peer"}),
    ("POST", "/submit", None),
    ("POST", "/approve", None),
    ("POST", "/reject", {"reason": "Peer reason"}),
    ("POST", "/assign", {"coordinator_id": str(_ANY_ID)}),
    ("POST", "/reassign", {"coordinator_id": str(_ANY_ID)}),
    ("GET", "/assignment-history", None),
    ("GET", "/clarifications", None),
    ("POST", "/clarifications", {"message": "Peer note"}),
    ("GET", "/venue-bookings", None),
    ("GET", "/venue-bookings/suitability", None),
    ("POST", "/venue-bookings", {}),
    ("GET", "/equipment-requirements", None),
    ("GET", "/equipment-requirements/history", None),
    ("GET", "/equipment-requirements/catalogue-types", None),
    ("POST", "/equipment-requirements", {}),
    ("PATCH", f"/equipment-requirements/{_ANY_ID}", {}),
    ("DELETE", f"/equipment-requirements/{_ANY_ID}", None),
    ("POST", f"/equipment-requirements/{_ANY_ID}/reserve", {}),
    ("GET", "/equipment-availability", None),
]


async def submitted_and_assigned(
    db: Session, owner: User, coordinator: User, make_client: MakeClient
) -> EventRequest:
    """A real submission by its owner, then the Lead's assignment arranged directly."""
    request = make_draft(db, owner)
    async with make_client(owner) as client:
        assert (await client.post(f"/api/event-requests/{request.id}/submit")).status_code == 200
    db.refresh(request)
    request.coordinator_id = coordinator.id
    db.flush()
    async with make_client(coordinator) as client:
        note = await client.post(
            f"/api/event-requests/{request.id}/clarifications", json={"message": "Internal"}
        )
    assert note.status_code == 201
    return request


def snapshot(db: Session, request: EventRequest) -> tuple[object, ...]:
    """The request's own state plus how many rows hang off it in each sub-resource."""
    db.expire_all()
    row = db.get(EventRequest, request.id)
    assert row is not None
    children = [
        db.query(model).filter(model.event_request_id == request.id).count()
        for model in (
            EventClarification,
            EventCoordinatorAssignment,
            EventEquipmentRequirement,
            VenueBooking,
        )
    ]
    return (row.name, row.status, row.coordinator_id, row.updated_at, *children)


@pytest.mark.story("SCRUM-112")
@pytest.mark.parametrize(("method", "suffix", "body"), PEER_ROUTES)
async def test_peer_is_refused_every_event_route_without_mutation(
    db: Session,
    make_user: MakeUser,
    make_client: MakeClient,
    method: str,
    suffix: str,
    body: dict[str, object] | None,
) -> None:
    """AC3, AC5, AC8: the request and each sub-resource are 403, and nothing changes."""
    owner = make_user("organiser")
    peer = make_user("organiser", organisation_id=owner.organisation_id)
    request = await submitted_and_assigned(db, owner, make_user("coordinator"), make_client)
    before = snapshot(db, request)

    async with make_client(peer) as client:
        response = await client.request(
            method, f"/api/event-requests/{request.id}{suffix}", json=body
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}
    assert snapshot(db, request) == before


@pytest.mark.story("SCRUM-112")
async def test_peer_is_refused_a_draft_and_its_requirements(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC3: a draft is refused to a peer too, not only a submitted request."""
    owner = make_user("organiser")
    peer = make_user("organiser", organisation_id=owner.organisation_id)
    draft = make_draft(db, owner)

    async with make_client(peer) as client:
        detail = await client.get(f"/api/event-requests/{draft.id}")
        requirements = await client.get(f"/api/event-requests/{draft.id}/equipment-requirements")

    assert detail.status_code == 403
    assert requirements.status_code == 403


@pytest.mark.story("SCRUM-112")
async def test_drafts_list_returns_only_the_callers_own_drafts(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC4: a peer's and an outsider's drafts are excluded, as are own submitted requests."""
    owner = make_user("organiser")
    peer = make_user("organiser", organisation_id=owner.organisation_id)
    outsider = make_user("organiser")
    own = [make_draft(db, owner, name=f"Own {n}") for n in range(2)]
    make_draft(db, peer, name="Peer draft")
    make_draft(db, outsider, name="Outsider draft")
    await submitted_and_assigned(db, owner, make_user("coordinator"), make_client)

    async with make_client(owner) as client:
        drafts = await client.get("/api/event-requests/drafts")
    async with make_client(peer) as client:
        peer_drafts = await client.get("/api/event-requests/drafts")

    assert drafts.status_code == 200
    assert sorted(row["id"] for row in drafts.json()) == sorted(str(row.id) for row in own)
    assert all(row["status"] == "draft" for row in drafts.json())
    assert [row["name"] for row in peer_drafts.json()] == ["Peer draft"]


@pytest.mark.story("SCRUM-112")
async def test_owner_keeps_full_access_to_own_requests_and_drafts(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC6: the owner still reads, edits and lists their own work."""
    owner = make_user("organiser")
    draft = make_draft(db, owner, name="Own draft")
    submitted = await submitted_and_assigned(db, owner, make_user("coordinator"), make_client)

    async with make_client(owner) as client:
        draft_detail = await client.get(f"/api/event-requests/{draft.id}")
        submitted_detail = await client.get(f"/api/event-requests/{submitted.id}")
        requirements = await client.get(
            f"/api/event-requests/{submitted.id}/equipment-requirements"
        )
        edited = await client.patch(f"/api/event-requests/{draft.id}", json={"name": "Renamed"})
        mine = await client.get("/api/event-requests")

    assert draft_detail.status_code == 200
    assert draft_detail.json()["purpose"] is not None
    assert submitted_detail.status_code == 200
    assert submitted_detail.json()["status"] == "submitted"
    assert requirements.status_code == 200
    assert edited.status_code == 200
    assert edited.json()["name"] == "Renamed"
    assert {row["id"] for row in mine.json()} == {str(draft.id), str(submitted.id)}


@pytest.mark.story("SCRUM-112")
async def test_assigned_coordinator_role_still_applies_to_a_peer_organiser(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC7: an Organiser+Coordinator account assigned to a peer's event keeps the
    assignee's access, but gains no owner rights from the shared organisation."""
    owner = make_user("organiser")
    dual = make_user("organiser", "coordinator", organisation_id=owner.organisation_id)
    request = await submitted_and_assigned(db, owner, dual, make_client)

    async with make_client(dual) as client:
        detail = await client.get(f"/api/event-requests/{request.id}")
        notes = await client.get(f"/api/event-requests/{request.id}/clarifications")
        edit = await client.patch(f"/api/event-requests/{request.id}", json={"name": "No"})

    assert detail.status_code == 200
    assert notes.status_code == 200
    assert edit.status_code == 403


@pytest.mark.story("SCRUM-112")
async def test_unassigned_coordinator_role_gives_a_peer_organiser_nothing(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC3, AC7: holding the Coordinator role is not the assignment; the shared
    organisation no longer fills the gap."""
    owner = make_user("organiser")
    dual = make_user("organiser", "coordinator", organisation_id=owner.organisation_id)
    request = await submitted_and_assigned(db, owner, make_user("coordinator"), make_client)

    async with make_client(dual) as client:
        detail = await client.get(f"/api/event-requests/{request.id}")

    assert detail.status_code == 403


@pytest.mark.story("SCRUM-112")
async def test_coordinator_lead_role_still_applies_to_a_peer_organiser(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC7: an Organiser+Lead account keeps allocation visibility of a peer's submitted
    event, and — like any Lead — still cannot see a draft."""
    owner = make_user("organiser")
    dual = make_user("organiser", "coordinator_lead", organisation_id=owner.organisation_id)
    request = await submitted_and_assigned(db, owner, make_user("coordinator"), make_client)
    draft = make_draft(db, owner)

    async with make_client(dual) as client:
        detail = await client.get(f"/api/event-requests/{request.id}")
        history = await client.get(f"/api/event-requests/{request.id}/assignment-history")
        draft_detail = await client.get(f"/api/event-requests/{draft.id}")

    assert detail.status_code == 200
    assert history.status_code == 200
    assert draft_detail.status_code == 403


@pytest.mark.story("SCRUM-112")
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/event-requests/{id}"),
        ("PATCH", "/api/event-requests/{id}"),
        ("GET", "/api/event-requests/{id}/equipment-requirements"),
        ("GET", "/api/event-requests/drafts"),
        ("GET", "/api/event-requests/organisation-calendar"),
    ],
)
async def test_unauthenticated_requests_get_401_without_mutation(
    db: Session, make_user: MakeUser, make_client: MakeClient, method: str, path: str
) -> None:
    """AC8: no token is a 401, before any access decision, and nothing changes."""
    request = make_draft(db, make_user("organiser"))
    before = snapshot(db, request)

    async with make_client(None) as client:
        body = {"name": "Anonymous"} if method == "PATCH" else None
        response = await client.request(method, path.format(id=request.id), json=body)

    assert response.status_code == 401
    assert snapshot(db, request) == before


@pytest.mark.story("SCRUM-112")
async def test_peer_draft_is_on_the_calendar_but_not_readable(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1, AC3: the calendar is the only window onto a peer's event."""
    owner = make_user("organiser")
    peer = make_user("organiser", organisation_id=owner.organisation_id)
    draft = make_draft(db, owner, name="Peer planning day")
    assert draft.status is EventStatus.DRAFT

    async with make_client(peer) as client:
        calendar = await client.get("/api/event-requests/organisation-calendar")
        detail = await client.get(f"/api/event-requests/{draft.id}")

    [entry] = calendar.json()
    assert set(entry) == {"id", "name", "start_at", "end_at", "status"}
    assert (entry["id"], entry["name"], entry["status"]) == (
        str(draft.id),
        "Peer planning day",
        "draft",
    )
    assert datetime.fromisoformat(entry["start_at"]) == draft.start_at
    assert datetime.fromisoformat(entry["end_at"]) == draft.end_at
    assert detail.status_code == 403
