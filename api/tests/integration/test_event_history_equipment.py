"""SCRUM-119 AC6: equipment entries, read through GET /event-requests/{id}/history.

Every record is made by its real writer: the requirement add and update (SCRUM-43), the
seed at approval, the reservation (SCRUM-53), the flag the update raises, and the release
a whole-event cancellation makes (SCRUM-115). Access is the SCRUM-88 route's, unchanged.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy.orm import Session

from domain.equipment_requirement import RequirementFields
from models.event_request import EventRequest
from models.user import User
from repositories import equipment_reservations as reservation_repo
from services import equipment_requirements as requirement_service
from services import equipment_reservations as reservation_service
from tests.integration.test_equipment_requirements import catalogue, planning_event
from tests.integration.test_submit_event_request import MakeClient, MakeUser


async def history(make_client: MakeClient, viewer: User, event: EventRequest) -> Any:
    async with make_client(viewer) as client:
        response = await client.get(f"/api/event-requests/{event.id}/history")
    assert response.status_code == 200
    return response.json()


def equipment(body: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in body if e["equipment_type"] is not None]


def planned(db: Session, make_user: MakeUser) -> tuple[EventRequest, User, User, str, datetime]:
    """An event in planning with its own catalogue type, and its owner and Coordinator."""
    event, coordinator = planning_event(db, make_user)
    kind = f"History kit {uuid.uuid4()}"
    catalogue(db, kind)
    owner = db.get(User, event.organiser_id)
    assert owner is not None
    return event, owner, coordinator, kind, datetime.now(UTC).replace(microsecond=0)


def everything(db: Session, make_user: MakeUser) -> tuple[EventRequest, User, User, User, str]:
    """Added (t), reserved (t+1m), updated and so flagged (t+2m), released (t+3m)."""
    event, owner, coordinator, kind, t = planned(db, make_user)
    tech = make_user("tech_support")
    fields = RequirementFields(equipment_type=kind, quantity=2, technical_requirements="HDMI")
    row = requirement_service.add(db, event, fields, coordinator.id, t)
    reservation_service.reserve(db, event.id, row.id, 2, tech.id, t + timedelta(minutes=1))
    requirement_service.update(
        db, event, row.id, {"quantity": 3}, coordinator.id, t + timedelta(minutes=2)
    )
    reservation_repo.release_for_event(db, event.id, coordinator.id, t + timedelta(minutes=3))
    db.flush()
    return event, owner, coordinator, tech, kind


@pytest.mark.story("SCRUM-119")
async def test_requirement_changes_and_reservation_lifecycle_appear_in_order(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, owner, coordinator, tech, kind = everything(db, make_user)

    rows = equipment(await history(make_client, owner, event))

    assert [(e["action"], e["actor_email"]) for e in rows] == [
        ("requirement_added", coordinator.email),
        ("equipment_reserved", tech.email),
        ("requirement_updated", coordinator.email),
        ("reservation_flagged", None),
        ("reservation_released", coordinator.email),
    ]
    assert {e["equipment_type"] for e in rows} == {kind}
    added, reserved, updated, flagged, released = rows
    assert added["changes"] == [
        {"field": "quantity", "label": "Quantity", "old": None, "new": "2"},
        {
            "field": "technical_requirements",
            "label": "Technical requirements",
            "old": None,
            "new": "HDMI",
        },
    ]
    assert updated["changes"][0] == {
        "field": "quantity",
        "label": "Quantity",
        "old": "2",
        "new": "3",
    }
    assert [e["quantity"] for e in (reserved, flagged, released)] == [2, 2, 2]
    assert (flagged["actor_id"], flagged["actor_email"]) == (None, None)
    assert flagged["occurred_at"] == updated["occurred_at"]
    assert reserved["source_id"] == flagged["source_id"] == released["source_id"]
    assert reserved["source_type"] == "equipment_reservation"
    assert added["source_type"] == "equipment_requirement_change"


@pytest.mark.story("SCRUM-119")
async def test_the_requirement_carried_across_at_approval_has_no_added_entry(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """SCRUM-43 writes no change row for the seeded requirement, so nothing is shown."""
    event, owner, _coordinator, kind, t = planned(db, make_user)
    event.equipment_requirement = kind
    requirement_service.seed_from_event(db, event, t)
    db.flush()

    assert equipment(await history(make_client, owner, event)) == []


@pytest.mark.story("SCRUM-119")
async def test_a_refused_requirement_change_leaves_no_entry(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC8: a change the writer refuses (no quantity) records nothing."""
    event, owner, coordinator, kind, t = planned(db, make_user)
    fields = RequirementFields(equipment_type=kind, quantity=None)

    with pytest.raises(requirement_service.InvalidRequirementError):
        requirement_service.add(db, event, fields, coordinator.id, t)

    assert equipment(await history(make_client, owner, event)) == []


@pytest.mark.story("SCRUM-119")
async def test_owner_assignee_and_lead_see_the_same_equipment_entries(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, owner, coordinator, _tech, _kind = everything(db, make_user)

    bodies = [
        await history(make_client, viewer, event)
        for viewer in (owner, coordinator, make_user("coordinator_lead"))
    ]

    assert len(equipment(bodies[0])) == 5
    assert all(body == bodies[0] for body in bodies)


@pytest.mark.story("SCRUM-119")
@pytest.mark.parametrize(
    "caller", ["reserving_tech_support", "unassigned_coordinator", "peer_organiser", "attendee"]
)
async def test_everyone_else_still_gets_a_bare_403(
    caller: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """Reserving the equipment gives Technical Support no access to the history."""
    event, owner, _coordinator, tech, _kind = everything(db, make_user)
    viewer = {
        "reserving_tech_support": lambda: tech,
        "unassigned_coordinator": lambda: make_user("coordinator"),
        "peer_organiser": lambda: make_user("organiser", organisation_id=owner.organisation_id),
        "attendee": lambda: make_user("attendee"),
    }[caller]()

    async with make_client(viewer) as client:
        response = await client.get(f"/api/event-requests/{event.id}/history")

    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}


@pytest.mark.story("SCRUM-119")
async def test_reading_the_equipment_entries_issues_only_selects(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, owner, coordinator, _tech, _kind = everything(db, make_user)
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
        for viewer in (owner, coordinator):
            await history(make_client, viewer, event)
    finally:
        sa_event.remove(connection, "before_cursor_execute", capture)
        sa_event.remove(db, "before_flush", count_flush)

    assert statements
    assert all(s.lstrip().upper().startswith("SELECT") for s in statements)
    assert flushes == []
