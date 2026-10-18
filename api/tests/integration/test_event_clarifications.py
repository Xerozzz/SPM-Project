"""SCRUM-106: clarification comments are internal notes for the assigned coordinator.

SCRUM-106 supersedes only SCRUM-30's organiser visibility/reply acceptance criteria:
the organiser list/response flow is gone, and notes are readable and writable solely
by the currently assigned coordinator. Storage (one chronological table with author
and timezone-aware timestamp) is unchanged from ADR-0010. TC-106-01 to TC-106-07
prove the backend boundary; TC-106-08 (unit) and TC-106-09 (E2E) live with the
frontend and E2E suites.
"""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from models.event_clarification import EventClarification
from models.event_request import EventRequest
from models.user import User
from tests.integration.test_submit_event_request import (
    MakeClient,
    MakeUser,
    make_draft,
)


async def submitted_request(db: Session, organiser: User, make_client: MakeClient) -> EventRequest:
    request = make_draft(db, organiser)
    async with make_client(organiser) as client:
        response = await client.post(f"/api/event-requests/{request.id}/submit")
    assert response.status_code == 200
    db.refresh(request)
    return request


def assign(db: Session, request: EventRequest, coordinator: User) -> EventRequest:
    """Arrange ownership directly: submission leaves requests unassigned (SCRUM-101)."""
    request.coordinator_id = coordinator.id
    db.flush()
    assert request.coordinator_id == coordinator.id
    return request


async def record_note(
    client: httpx.AsyncClient, request: EventRequest, message: str = "Called the venue; layout TBC."
) -> httpx.Response:
    return await client.post(
        f"/api/event-requests/{request.id}/clarifications", json={"message": message}
    )


def note_count(db: Session, request: EventRequest) -> int:
    return (
        db.query(EventClarification)
        .filter(EventClarification.event_request_id == request.id)
        .count()
    )


# ------------------------------------------------------------------ TC-106-01


@pytest.mark.story("SCRUM-106")
async def test_assigned_coordinator_records_minimally_non_blank_note(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1: a single non-whitespace character records a note with event, author,
    content and a timezone-aware timestamp."""
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = assign(db, await submitted_request(db, organiser, make_client), coordinator)

    async with make_client(coordinator) as client:
        response = await record_note(client, request, "x")

    assert response.status_code == 201
    body = response.json()
    assert body["event_request_id"] == str(request.id)
    assert body["author_id"] == str(coordinator.id)
    assert body["kind"] == "request"
    assert body["message"] == "x"
    created_at = datetime.fromisoformat(body["created_at"].replace("Z", "+00:00"))
    assert created_at.tzinfo is not None
    assert abs(datetime.now(UTC) - created_at) < timedelta(seconds=30)


# ------------------------------------------------------------------ TC-106-02


@pytest.mark.story("SCRUM-106")
@pytest.mark.parametrize("message", ["", "   \n\t"])
async def test_blank_notes_are_refused_without_creating_records(
    message: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC3: empty and whitespace-only notes are refused, create zero records, and
    the minimally non-blank boundary case still succeeds afterwards."""
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = assign(db, await submitted_request(db, organiser, make_client), coordinator)

    async with make_client(coordinator) as client:
        refused = await record_note(client, request, message)
        assert refused.status_code == 422
        accepted = await record_note(client, request, "x")
        assert accepted.status_code == 201
        history = await client.get(f"/api/event-requests/{request.id}/clarifications")

    assert history.status_code == 200
    assert [entry["message"] for entry in history.json()] == ["x"]


# ------------------------------------------------------------------ TC-106-03


@pytest.mark.story("SCRUM-106")
async def test_assigned_coordinator_reads_notes_in_deterministic_order(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC2: zero notes read back as an empty collection; one then several notes
    read back in deterministic chronological order."""
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = assign(db, await submitted_request(db, organiser, make_client), coordinator)

    async with make_client(coordinator) as client:
        empty = await client.get(f"/api/event-requests/{request.id}/clarifications")
        assert empty.status_code == 200
        assert empty.json() == []

        for message in ("First note", "Second note", "Third note"):
            created = await record_note(client, request, message)
            assert created.status_code == 201

        history = await client.get(f"/api/event-requests/{request.id}/clarifications")

    assert history.status_code == 200
    assert [entry["message"] for entry in history.json()] == [
        "First note",
        "Second note",
        "Third note",
    ]


# ------------------------------------------------------------------ TC-106-04


@pytest.mark.story("SCRUM-106")
@pytest.mark.parametrize("same_organisation", [False, True])
async def test_organisers_cannot_list_create_or_respond(
    same_organisation: bool, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC4: the owning organiser — and another organiser in the same organisation —
    cannot list or record notes, and the removed response endpoint stays gone. Every
    refusal carries no note content."""
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = assign(db, await submitted_request(db, organiser, make_client), coordinator)
    async with make_client(coordinator) as client:
        assert (await record_note(client, request, "Internal only")).status_code == 201

    viewer = (
        organiser
        if not same_organisation
        else make_user("organiser", organisation_id=organiser.organisation_id)
    )
    async with make_client(viewer) as client:
        history = await client.get(f"/api/event-requests/{request.id}/clarifications")
        created = await record_note(client, request, "An organiser note")
        answered = await client.post(
            f"/api/event-requests/{request.id}/clarifications/responses",
            json={"message": "An organiser response"},
        )

    assert history.status_code == 403
    assert history.json() == {"detail": "Forbidden"}
    assert created.status_code == 403
    assert answered.status_code == 404
    assert note_count(db, request) == 1


# ------------------------------------------------------------------ TC-106-05


@pytest.mark.story("SCRUM-106")
@pytest.mark.parametrize("caller", ["unassigned", "other-event"])
@pytest.mark.parametrize("operation", ["list", "create"])
async def test_non_assigned_coordinators_are_refused_without_mutation(
    caller: str, operation: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC5: an unassigned coordinator and one assigned to another event are refused
    on list and create alike, with no mutation and no content disclosure."""
    organiser = make_user("organiser")
    owner = make_user("coordinator")
    other_owner = make_user("coordinator")
    outsider = make_user("coordinator")
    request = assign(db, await submitted_request(db, organiser, make_client), owner)
    other_request = assign(db, await submitted_request(db, organiser, make_client), other_owner)
    async with make_client(owner) as client:
        assert (await record_note(client, request, "Internal only")).status_code == 201
    before = note_count(db, request)

    viewer = outsider if caller == "unassigned" else other_owner
    # The other-event coordinator acts on the event they do NOT own; the unassigned
    # coordinator acts on an event owned by someone else.
    async with make_client(viewer) as client:
        if operation == "list":
            response = await client.get(f"/api/event-requests/{request.id}/clarifications")
        else:
            response = await record_note(client, request, "Snooping note")

    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}
    assert note_count(db, request) == before
    assert note_count(db, other_request) == 0


# ------------------------------------------------------------------ TC-106-06


@pytest.mark.story("SCRUM-106")
async def test_reassignment_transfers_note_access(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC6: after a Lead reassigns A to B, A loses list and create access while B
    reads the existing notes and adds another. Rows are never copied or rewritten."""
    organiser = make_user("organiser")
    outgoing = make_user("coordinator")
    incoming = make_user("coordinator")
    lead = make_user("coordinator_lead")
    request = assign(db, await submitted_request(db, organiser, make_client), outgoing)
    async with make_client(outgoing) as client:
        assert (await record_note(client, request, "Handoff note")).status_code == 201

    async with make_client(lead) as client:
        reassigned = await client.post(
            f"/api/event-requests/{request.id}/reassign",
            json={
                "coordinator_id": str(incoming.id),
                "expected_current_coordinator_id": str(outgoing.id),
            },
        )
    assert reassigned.status_code == 200

    async with make_client(outgoing) as client:
        lost_list = await client.get(f"/api/event-requests/{request.id}/clarifications")
        lost_create = await record_note(client, request, "Late note from A")
    async with make_client(incoming) as client:
        history = await client.get(f"/api/event-requests/{request.id}/clarifications")
        added = await record_note(client, request, "Follow-up from B")
        updated = await client.get(f"/api/event-requests/{request.id}/clarifications")

    assert lost_list.status_code == 403
    assert lost_create.status_code == 403
    assert history.status_code == 200
    assert [entry["message"] for entry in history.json()] == ["Handoff note"]
    assert added.status_code == 201
    assert [entry["message"] for entry in updated.json()] == ["Handoff note", "Follow-up from B"]


# ------------------------------------------------------------------ TC-106-07


@pytest.mark.story("SCRUM-106")
async def test_recording_notes_leaves_status_unchanged_and_append_only(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC7/AC8: several notes leave the event status untouched, introduce no
    clarification status, and the collection accepts no overwrite or delete."""
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = assign(db, await submitted_request(db, organiser, make_client), coordinator)
    assert "clarification" not in {state.value for state in EventStatus}
    before = request.status

    async with make_client(coordinator) as client:
        for message in ("First note", "Second note", "Third note"):
            created = await record_note(client, request, message)
            assert created.status_code == 201
        overwrite = await client.put(
            f"/api/event-requests/{request.id}/clarifications", json={"message": "Edited"}
        )
        remove = await client.delete(f"/api/event-requests/{request.id}/clarifications")

    db.refresh(request)
    assert request.status is EventStatus.SUBMITTED
    assert request.status == before
    assert overwrite.status_code == 405
    assert remove.status_code == 405
    assert note_count(db, request) == 3
