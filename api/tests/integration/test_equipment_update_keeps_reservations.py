"""SCRUM-93 AC6 and AC7: editing a catalogue entry leaves events' equipment alone.

Requirements and reservations are made against an equipment type, not a catalogue row
(ADR-0024, ADR-0038). So an edit that keeps the type, including a change to its
operational status, must not touch either of them.
"""

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from models.equipment import Equipment
from models.equipment_reservation import EquipmentReservation
from models.event_equipment_requirement import EventEquipmentRequirement
from models.event_request import EventRequest
from tests.integration.test_equipment_availability import entry, new_type
from tests.integration.test_equipment_requirements import planning_event
from tests.integration.test_reserve_equipment import reserve
from tests.integration.test_review_equipment_requirements import requirement
from tests.integration.test_submit_event_request import MakeClient, MakeUser


def edit_body(item: Equipment, **changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "equipment_type": item.equipment_type,
        "description": item.description,
        "total_quantity": item.total_quantity,
        "location": item.location,
        "operational_status": item.operational_status,
    }
    values.update(changes)
    return values


Rows = list[tuple[Any, ...]]


def snapshot(db: Session, event: EventRequest) -> tuple[Rows, Rows]:
    db.expire_all()
    requirements = db.scalars(
        select(EventEquipmentRequirement).where(
            EventEquipmentRequirement.event_request_id == event.id
        )
    )
    reservations = db.scalars(
        select(EquipmentReservation).where(EquipmentReservation.event_request_id == event.id)
    )
    return (
        [(r.id, r.equipment_type, r.quantity, r.review_status, r.removed_at) for r in requirements],
        [
            (r.id, r.requirement_id, r.equipment_type, r.quantity, r.released_at, r.flagged_at)
            for r in reservations
        ],
    )


async def reserved_event(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> tuple[EventRequest, Equipment]:
    event, _ = planning_event(db, make_user)
    equipment_type = new_type()
    item = entry(db, equipment_type, 5)
    row = requirement(db, event, equipment_type, quantity=2)
    async with make_client(make_user("tech_support")) as client:
        response = await reserve(client, event, row)
    assert response.status_code == 201, response.text
    return event, item


@pytest.mark.story("SCRUM-93")
async def test_editing_an_entry_keeps_requirements_and_reservations_on_it(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC6: a new location, quantity and description leave the event's equipment as it was."""
    event, item = await reserved_event(db, make_user, make_client)
    before = snapshot(db, event)

    async with make_client(make_user("tech_support")) as client:
        response = await client.put(
            f"/api/equipment/{item.id}",
            json=edit_body(
                item, location="Lecture Theatre Store", total_quantity=8, description="Moved"
            ),
        )

    assert response.status_code == 200, response.text
    assert response.json()["location"] == "Lecture Theatre Store"
    after = snapshot(db, event)
    assert after == before
    [(_, requirement_id, equipment_type, quantity, released_at, _)] = after[1]
    assert (equipment_type, quantity, released_at) == (item.equipment_type, 2, None)
    assert requirement_id == after[0][0][0]


@pytest.mark.parametrize("status", ["Damaged", "Under Maintenance"])
@pytest.mark.story("SCRUM-93")
async def test_changing_operational_status_does_not_cancel_reservations(
    db: Session, make_user: MakeUser, make_client: MakeClient, status: str
) -> None:
    """AC7: taking an entry out of service does not release or flag what is reserved."""
    event, item = await reserved_event(db, make_user, make_client)
    before = snapshot(db, event)

    async with make_client(make_user("tech_support")) as client:
        response = await client.put(
            f"/api/equipment/{item.id}", json=edit_body(item, operational_status=status)
        )

    assert response.status_code == 200, response.text
    assert response.json()["operational_status"] == status
    after = snapshot(db, event)
    assert after == before
    [reservation] = after[1]
    assert reservation[4:] == (None, None)
