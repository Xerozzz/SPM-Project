"""SCRUM-43: the assigned Coordinator maintains an event's equipment requirements.

Against real PostgreSQL, so the partial unique index and the audit rows are exercised
rather than just the pure rules. The arrangement throughout is one approved event with an
assigned coordinator and a catalogue holding Projector and Microphone.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.equipment_requirement import RequirementReview
from domain.event_status import EventStatus
from models.equipment import Equipment
from models.equipment_requirement_change import EquipmentRequirementChange
from models.event_equipment_requirement import EventEquipmentRequirement
from models.event_request import EventRequest
from models.user import User
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_submit_venue_booking import approved_event


def catalogue(db: Session, *types: str) -> None:
    for equipment_type in types:
        db.add(
            Equipment(
                equipment_type=equipment_type,
                description=None,
                total_quantity=10,
                location="Store room",
                operational_status="operational",
            )
        )
    db.flush()


def planning_event(
    db: Session, make_user: MakeUser, **changes: object
) -> tuple[EventRequest, User]:
    """An approved event with its coordinator assigned, which is AC2's maintainable state."""
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator, **changes)
    return event, coordinator


def url(event: EventRequest, suffix: str = "") -> str:
    return f"/api/event-requests/{event.id}/equipment-requirements{suffix}"


def body(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "equipment_type": "Projector",
        "quantity": 2,
        "technical_requirements": "Needs an HDMI cable",
    }
    values.update(overrides)
    return values


def named_fields(response: httpx.Response) -> list[str]:
    detail: list[dict[str, Any]] = response.json()["detail"]
    return [problem["field"] for problem in detail]


def stored(db: Session, event: EventRequest) -> list[EventEquipmentRequirement]:
    return list(
        db.scalars(
            select(EventEquipmentRequirement)
            .where(EventEquipmentRequirement.event_request_id == event.id)
            .order_by(EventEquipmentRequirement.created_at)
        )
    )


def audit(db: Session, event: EventRequest) -> list[EquipmentRequirementChange]:
    return list(
        db.scalars(
            select(EquipmentRequirementChange)
            .where(EquipmentRequirementChange.event_request_id == event.id)
            .order_by(EquipmentRequirementChange.changed_at, EquipmentRequirementChange.id)
        )
    )


# --------------------------------------------------------------------------- AC3


@pytest.mark.story("SCRUM-43")
async def test_the_coordinator_can_add_a_requirement(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    catalogue(db, "Projector")
    event, coordinator = planning_event(db, make_user)

    async with make_client(coordinator) as client:
        response = await client.post(url(event), json=body())

    assert response.status_code == 201, response.text
    assert response.json()["equipment_type"] == "Projector"
    assert response.json()["quantity"] == 2
    # AC5: nobody has assessed it, so it starts pending.
    assert response.json()["review_status"] == "pending_review"


@pytest.mark.story("SCRUM-43")
@pytest.mark.parametrize(
    ("field", "value"),
    [("quantity", 0), ("quantity", -1), ("quantity", None), ("equipment_type", None)],
)
async def test_an_invalid_requirement_is_refused_with_the_field_named(
    db: Session, make_user: MakeUser, make_client: MakeClient, field: str, value: object
) -> None:
    catalogue(db, "Projector")
    event, coordinator = planning_event(db, make_user)

    async with make_client(coordinator) as client:
        response = await client.post(url(event), json=body(**{field: value}))

    assert response.status_code == 422
    assert named_fields(response) == [field]
    assert stored(db, event) == []


@pytest.mark.story("SCRUM-43")
async def test_a_type_outside_the_active_catalogue_is_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # AC3: the catalogue is the vocabulary, and a deactivated entry is not in it.
    catalogue(db, "Projector")
    deactivated = Equipment(
        equipment_type="Smoke machine",
        description=None,
        total_quantity=1,
        location="Store room",
        operational_status="operational",
        is_active=False,
    )
    db.add(deactivated)
    db.flush()
    event, coordinator = planning_event(db, make_user)

    async with make_client(coordinator) as client:
        response = await client.post(url(event), json=body(equipment_type="Smoke machine"))

    assert response.status_code == 422
    assert named_fields(response) == ["equipment_type"]


# --------------------------------------------------------------------------- AC4


@pytest.mark.story("SCRUM-43")
async def test_the_same_type_twice_is_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    catalogue(db, "Projector")
    event, coordinator = planning_event(db, make_user)

    async with make_client(coordinator) as client:
        first = await client.post(url(event), json=body())
        second = await client.post(url(event), json=body(quantity=5))

    assert first.status_code == 201
    assert second.status_code == 422
    assert named_fields(second) == ["equipment_type"]
    assert len(stored(db, event)) == 1


@pytest.mark.story("SCRUM-43")
async def test_a_removed_type_can_be_asked_for_again(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # The uniqueness in AC4 is about live lines. A plain unique constraint would make soft
    # removal a one-way door, which is not what AC7 asks for.
    catalogue(db, "Projector")
    event, coordinator = planning_event(db, make_user)

    async with make_client(coordinator) as client:
        added = await client.post(url(event), json=body())
        await client.delete(url(event, f"/{added.json()['id']}"))
        again = await client.post(url(event), json=body(quantity=4))

    assert again.status_code == 201, again.text
    assert again.json()["quantity"] == 4
    assert len(stored(db, event)) == 2


# --------------------------------------------------------------------------- AC5


@pytest.mark.story("SCRUM-43")
async def test_changing_a_requirement_sends_it_back_for_review(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    catalogue(db, "Projector")
    event, coordinator = planning_event(db, make_user)

    async with make_client(coordinator) as client:
        added = await client.post(url(event), json=body())
        requirement_id = added.json()["id"]
        # Stand in for SCRUM-44 having assessed it, which is the state AC5 must undo.
        reviewed = db.get(EventEquipmentRequirement, uuid.UUID(requirement_id))
        assert reviewed is not None
        reviewed.review_status = RequirementReview.AVAILABLE
        db.flush()
        changed = await client.patch(url(event, f"/{requirement_id}"), json={"quantity": 5})

    assert changed.status_code == 200, changed.text
    assert changed.json()["quantity"] == 5
    assert changed.json()["review_status"] == "pending_review"


# --------------------------------------------------------------------------- AC7


@pytest.mark.story("SCRUM-43")
async def test_a_removed_requirement_leaves_the_live_list_but_stays_in_history(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    catalogue(db, "Projector")
    event, coordinator = planning_event(db, make_user)

    async with make_client(coordinator) as client:
        added = await client.post(url(event), json=body())
        await client.delete(url(event, f"/{added.json()['id']}"))
        live = await client.get(url(event))
        history = await client.get(url(event, "/history"))

    assert live.json() == []
    # The row is still there, which is what keeps it identifiable (AC7).
    assert len(stored(db, event)) == 1
    assert [entry["action"] for entry in history.json()] == ["added", "removed"]


@pytest.mark.story("SCRUM-43")
async def test_removing_a_requirement_twice_is_not_found(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    catalogue(db, "Projector")
    event, coordinator = planning_event(db, make_user)

    async with make_client(coordinator) as client:
        added = await client.post(url(event), json=body())
        await client.delete(url(event, f"/{added.json()['id']}"))
        again = await client.delete(url(event, f"/{added.json()['id']}"))

    assert again.status_code == 404


# --------------------------------------------------------------------------- AC8


@pytest.mark.story("SCRUM-43")
async def test_every_change_records_who_what_and_both_sides(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    catalogue(db, "Projector")
    event, coordinator = planning_event(db, make_user)

    async with make_client(coordinator) as client:
        added = await client.post(url(event), json=body())
        await client.patch(url(event, f"/{added.json()['id']}"), json={"quantity": 7})
        await client.delete(url(event, f"/{added.json()['id']}"))

    rows = audit(db, event)
    assert [row.action for row in rows] == ["added", "updated", "removed"]
    assert {row.changed_by_id for row in rows} == {coordinator.id}
    assert (rows[0].old_quantity, rows[0].new_quantity) == (None, 2)
    assert (rows[1].old_quantity, rows[1].new_quantity) == (2, 7)
    assert (rows[2].old_quantity, rows[2].new_quantity) == (7, None)


@pytest.mark.story("SCRUM-43")
async def test_a_refused_change_records_nothing(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    catalogue(db, "Projector")
    event, coordinator = planning_event(db, make_user)

    async with make_client(coordinator) as client:
        response = await client.post(url(event), json=body(quantity=0))

    assert response.status_code == 422
    assert audit(db, event) == []


# --------------------------------------------------------------------------- AC1


@pytest.mark.story("SCRUM-43")
async def test_approval_carries_the_organisers_choice_across(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1: what the organiser asked for is the Coordinator's first requirement.

    Approval is the handoff: before it the organiser owns the single type they picked
    (ADR-0024), after it the Coordinator maintains records. Without this an event approved
    today would start with an empty list and the Coordinator would type it again.
    """
    catalogue(db, "Projector")
    event, coordinator = planning_event(db, make_user, equipment_requirement="Projector")

    async with make_client(coordinator) as client:
        response = await client.get(url(event))

    assert [row["equipment_type"] for row in response.json()] == ["Projector"]
    assert response.json()[0]["quantity"] == 1
    assert response.json()[0]["review_status"] == "pending_review"
    # Nobody did this, so nothing is recorded as having been done (AC8 is about people).
    assert audit(db, event) == []


# --------------------------------------------------------------------- AC2 and AC10


@pytest.mark.story("SCRUM-43")
@pytest.mark.parametrize("role", ["organiser", "venue_staff", "attendee"])
async def test_other_roles_cannot_maintain_requirements(
    db: Session, make_user: MakeUser, make_client: MakeClient, role: str
) -> None:
    catalogue(db, "Projector")
    event, _ = planning_event(db, make_user)

    async with make_client(make_user(role)) as client:
        response = await client.post(url(event), json=body())

    assert response.status_code == 403
    assert stored(db, event) == []


@pytest.mark.story("SCRUM-43")
async def test_another_coordinator_cannot_maintain_someone_elses_event(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # AC10: the *currently assigned* coordinator. Rights follow the assignment.
    catalogue(db, "Projector")
    event, _ = planning_event(db, make_user)

    async with make_client(make_user("coordinator")) as client:
        response = await client.post(url(event), json=body())

    assert response.status_code == 403


@pytest.mark.story("SCRUM-43")
async def test_rights_move_with_a_reassignment(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # AC10's last clause. The rule reads the event's coordinator each time rather than
    # remembering who it was, so this needs no code of its own; the test says so.
    catalogue(db, "Projector")
    event, first = planning_event(db, make_user)
    second = make_user("coordinator")
    event.coordinator_id = second.id
    db.flush()

    async with make_client(second) as client:
        now_allowed = await client.post(url(event), json=body())
    async with make_client(first) as client:
        now_refused = await client.post(url(event), json=body(equipment_type="Projector"))

    assert now_allowed.status_code == 201, now_allowed.text
    assert now_refused.status_code == 403


@pytest.mark.story("SCRUM-43")
@pytest.mark.parametrize(
    "status",
    [EventStatus.DRAFT, EventStatus.SUBMITTED, EventStatus.CONFIRMED, EventStatus.REJECTED],
)
async def test_requirements_cannot_be_changed_outside_planning(
    db: Session, make_user: MakeUser, make_client: MakeClient, status: EventStatus
) -> None:
    # AC2: only while the event is being planned, which this codebase calls APPROVED.
    # AC11 sends a change after confirmation through the significant-change process.
    catalogue(db, "Projector")
    event, coordinator = planning_event(db, make_user)
    event.status = status
    db.flush()

    async with make_client(coordinator) as client:
        response = await client.post(url(event), json=body())

    assert response.status_code == 403


@pytest.mark.story("SCRUM-43")
async def test_the_organiser_can_read_what_their_event_needs(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # Maintaining is the coordinator's; reading follows ordinary event visibility, so the
    # organiser can see what is being arranged for them without being able to change it.
    catalogue(db, "Projector")
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    event = approved_event(db, organiser, coordinator)

    async with make_client(coordinator) as client:
        await client.post(url(event), json=body())
    async with make_client(organiser) as client:
        readable = await client.get(url(event))
        writable = await client.post(url(event), json=body(equipment_type="Projector"))

    assert [row["equipment_type"] for row in readable.json()] == ["Projector"]
    assert writable.status_code == 403


# --------------------------------------------------------------------------- AC9


@pytest.mark.story("SCRUM-43")
async def test_recording_a_requirement_reserves_nothing(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # AC9: a requirement says what is needed. SCRUM-53 is what commits anything, and until
    # it exists the catalogue's stock must be untouched by any of this.
    catalogue(db, "Projector")
    event, coordinator = planning_event(db, make_user)
    before = [(e.id, e.total_quantity, e.is_active) for e in db.scalars(select(Equipment))]

    async with make_client(coordinator) as client:
        await client.post(url(event), json=body(quantity=99))

    db.expire_all()
    assert [(e.id, e.total_quantity, e.is_active) for e in db.scalars(select(Equipment))] == before


@pytest.mark.story("SCRUM-43")
async def test_a_requirement_for_another_event_is_not_found(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # Reported as missing rather than forbidden, so the route cannot be used to find out
    # that an id exists on someone else's event.
    catalogue(db, "Projector")
    mine, coordinator = planning_event(db, make_user)
    theirs, other = planning_event(db, make_user)

    async with make_client(other) as client:
        added = await client.post(url(theirs), json=body())
    async with make_client(coordinator) as client:
        response = await client.patch(url(mine, f"/{added.json()['id']}"), json={"quantity": 3})

    assert response.status_code == 404


@pytest.mark.story("SCRUM-43")
async def test_the_history_starts_empty(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    catalogue(db, "Projector")
    event, coordinator = planning_event(db, make_user)

    async with make_client(coordinator) as client:
        response = await client.get(url(event, "/history"))

    assert response.status_code == 200
    assert response.json() == []
    assert datetime.now(UTC) is not None
