"""SCRUM-104: a Coordinator sees only events currently assigned to them.

TC-104-01 pins the reviewable list scope (zero, one, several). TC-104-02 pins the
object-level refusal without disclosure. TC-104-03 pins access transfer on reassign.
TC-104-04 pins equal Lead allocation visibility. TC-104-05 pins dual Lead+Coordinator
accounts keeping Lead allocation visibility.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from models.event_request import EventRequest
from models.user import User
from tests.integration.test_submit_event_request import make_draft

MakeUser = Callable[..., User]
MakeClient = Callable[[User | None], httpx.AsyncClient]


def _submitted(
    db: Session,
    organiser: User,
    coordinator: User | None,
    submitted_at: datetime,
) -> EventRequest:
    """A Submitted request with exact ownership, so tests control assignment directly."""
    request = make_draft(db, organiser)
    request.status = EventStatus.SUBMITTED
    request.submitted_at = submitted_at
    request.coordinator_id = coordinator.id if coordinator is not None else None
    db.flush()
    return request


# ------------------------------------------------------------------ TC-104-01


@pytest.mark.story("SCRUM-104")
async def test_reviewable_lists_only_events_assigned_to_the_caller(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1: zero, one and several assigned events across Coordinators."""
    organiser = make_user("organiser")
    first = make_user("coordinator")
    second = make_user("coordinator")
    nobody = make_user("coordinator")
    base = datetime(2026, 5, 1, 9, 0, tzinfo=UTC)
    mine_a = _submitted(db, organiser, first, base)
    mine_b = _submitted(db, organiser, first, base + timedelta(hours=1))
    theirs = _submitted(db, organiser, second, base + timedelta(hours=2))
    _submitted(db, organiser, None, base + timedelta(hours=3))

    async with make_client(first) as client:
        mine = await client.get("/api/event-requests/reviewable")
    async with make_client(second) as client:
        other = await client.get("/api/event-requests/reviewable")
    async with make_client(nobody) as client:
        empty = await client.get("/api/event-requests/reviewable")

    assert mine.status_code == 200
    assert [row["id"] for row in mine.json()] == [str(mine_a.id), str(mine_b.id)]
    assert other.status_code == 200
    assert [row["id"] for row in other.json()] == [str(theirs.id)]
    assert empty.status_code == 200
    assert empty.json() == []


# ------------------------------------------------------------------ TC-104-02


@pytest.mark.story("SCRUM-104")
async def test_ordinary_coordinator_cannot_open_unassigned_or_others_events(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC2: unassigned and another Coordinator's events refuse view and history."""
    organiser = make_user("organiser")
    assigned = make_user("coordinator")
    outsider = make_user("coordinator")
    base = datetime(2026, 5, 1, 9, 0, tzinfo=UTC)
    unassigned = _submitted(db, organiser, None, base)
    owned = _submitted(db, organiser, assigned, base + timedelta(hours=1))

    async with make_client(assigned) as client:
        clarification = await client.post(
            f"/api/event-requests/{owned.id}/clarifications",
            json={"message": "Which room layout is needed?"},
        )
    assert clarification.status_code == 201

    async with make_client(outsider) as client:
        unassigned_view = await client.get(f"/api/event-requests/{unassigned.id}")
        owned_view = await client.get(f"/api/event-requests/{owned.id}")
        unassigned_history = await client.get(f"/api/event-requests/{unassigned.id}/clarifications")
        owned_history = await client.get(f"/api/event-requests/{owned.id}/clarifications")

    for response in (unassigned_view, owned_view, unassigned_history, owned_history):
        assert response.status_code == 403
        assert response.json() == {"detail": "Forbidden"}
        assert "Orientation Day" not in response.text

    async with make_client(assigned) as client:
        control = await client.get(f"/api/event-requests/{owned.id}")
    assert control.status_code == 200


# ------------------------------------------------------------------ TC-104-03


@pytest.mark.story("SCRUM-104")
async def test_reassignment_moves_access_from_outgoing_to_incoming_coordinator(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC3: after A→B the outgoing Coordinator is refused and the incoming one is let in."""
    organiser = make_user("organiser")
    outgoing = make_user("coordinator")
    incoming = make_user("coordinator")
    lead = make_user("coordinator_lead")
    request = _submitted(db, organiser, outgoing, datetime(2026, 5, 1, 9, 0, tzinfo=UTC))

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
        lost_view = await client.get(f"/api/event-requests/{request.id}")
        lost_list = await client.get("/api/event-requests/reviewable")
        lost_decision = await client.post(f"/api/event-requests/{request.id}/approve")
    async with make_client(incoming) as client:
        gained_view = await client.get(f"/api/event-requests/{request.id}")
        gained_list = await client.get("/api/event-requests/reviewable")

    assert lost_view.status_code == 403
    assert lost_list.status_code == 200
    assert all(row["id"] != str(request.id) for row in lost_list.json())
    assert lost_decision.status_code == 403
    assert gained_view.status_code == 200
    assert gained_view.json()["id"] == str(request.id)
    assert [row["id"] for row in gained_list.json()] == [str(request.id)]


# ------------------------------------------------------------------ TC-104-04


@pytest.mark.story("SCRUM-104")
async def test_two_leads_see_the_same_allocation_data(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC4: every Lead sees all unassigned and assigned events needed for allocation."""
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    first_lead = make_user("coordinator_lead")
    second_lead = make_user("coordinator_lead")
    base = datetime(2026, 5, 1, 9, 0, tzinfo=UTC)
    _submitted(db, organiser, None, base)
    _submitted(db, organiser, coordinator, base + timedelta(hours=1))

    async with make_client(first_lead) as client:
        first_unassigned = await client.get("/api/event-requests/unassigned")
        first_active = await client.get("/api/event-requests/active-assignments")
    async with make_client(second_lead) as client:
        second_unassigned = await client.get("/api/event-requests/unassigned")
        second_active = await client.get("/api/event-requests/active-assignments")

    assert first_unassigned.status_code == 200
    assert second_unassigned.status_code == 200
    assert first_unassigned.json() == second_unassigned.json()
    assert len(first_unassigned.json()) == 1
    assert first_active.status_code == 200
    assert second_active.status_code == 200
    assert first_active.json() == second_active.json()
    assert len(first_active.json()) == 2


# ------------------------------------------------------------------ TC-104-05


@pytest.mark.story("SCRUM-104")
async def test_dual_lead_and_coordinator_keeps_lead_allocation_visibility(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC5: a multi-role account keeps Lead allocation views for others' events."""
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    dual = make_user("coordinator", "coordinator_lead")
    request = _submitted(db, organiser, coordinator, datetime(2026, 5, 1, 9, 0, tzinfo=UTC))

    async with make_client(dual) as client:
        unassigned = await client.get("/api/event-requests/unassigned")
        active = await client.get("/api/event-requests/active-assignments")
        single = await client.get(f"/api/event-requests/{request.id}")

    assert unassigned.status_code == 200
    assert active.status_code == 200
    assert any(row["id"] == str(request.id) for row in active.json())
    assert single.status_code == 200
    assert single.json()["id"] == str(request.id)
