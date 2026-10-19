"""SCRUM-52: check whether there is enough equipment for an event's requirements.

Against real PostgreSQL, reusing SCRUM-43's planning event and SCRUM-44's requirement
helper. Every test invents its own equipment types, so stock seeded by other helpers (the
draft fixture adds a Projector) never leaks into the sums asserted here.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.equipment import OPERATIONAL_STATUSES
from domain.equipment_availability import IN_SERVICE_STATUS
from domain.event_status import EventStatus
from models.equipment import Equipment
from models.event_equipment_requirement import EventEquipmentRequirement
from models.event_request import EventRequest
from models.user import User
from repositories import equipment as catalogue_repo
from tests.integration.test_equipment_requirements import planning_event
from tests.integration.test_review_equipment_requirements import requirement
from tests.integration.test_submit_event_request import MakeClient, MakeUser

OTHER_ROLES = ["organiser", "coordinator_lead", "venue_staff", "attendee"]


def url(event: EventRequest) -> str:
    return f"/api/event-requests/{event.id}/equipment-availability"


def new_type() -> str:
    return f"Type {uuid.uuid4()}"


def entry(
    db: Session,
    equipment_type: str,
    quantity: int,
    *,
    status: str = IN_SERVICE_STATUS,
    is_active: bool = True,
) -> Equipment:
    row = Equipment(
        equipment_type=equipment_type,
        description=None,
        total_quantity=quantity,
        location=f"Store {uuid.uuid4()}",
        operational_status=status,
        is_active=is_active,
    )
    db.add(row)
    db.flush()
    return row


def by_type(response_json: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["equipment_type"]: row for row in response_json}


# ------------------------------------------------------------------- AC1 and AC4


@pytest.mark.story("SCRUM-52")
async def test_tech_support_sees_each_requirement_with_its_window_and_result(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = planning_event(db, make_user)
    plenty, short, none = new_type(), new_type(), new_type()
    entry(db, plenty, 5)
    entry(db, short, 1)
    row = requirement(db, event, plenty, quantity=2)
    requirement(db, event, short, quantity=3)
    requirement(db, event, none, quantity=1)

    async with make_client(make_user("tech_support")) as client:
        response = await client.get(url(event))

    assert response.status_code == 200, response.text
    assert [r["equipment_type"] for r in response.json()] == [plenty, short, none]
    rows = by_type(response.json())
    assert event.start_at is not None and event.end_at is not None
    assert rows[plenty]["id"] == str(row.id)
    assert rows[plenty]["quantity"] == 2
    assert rows[plenty]["technical_requirements"] == "Needs an HDMI cable"
    assert datetime.fromisoformat(rows[plenty]["event_start_at"]) == event.start_at
    assert datetime.fromisoformat(rows[plenty]["event_end_at"]) == event.end_at
    assert {k: rows[plenty][k] for k in ("stock", "reserved", "available", "result")} == {
        "stock": 5,
        "reserved": 0,
        "available": 5,
        "result": "available",
    }
    assert rows[short]["result"] == "partially_available"
    assert rows[none]["result"] == "unavailable"
    assert rows[none]["stock"] == 0


@pytest.mark.story("SCRUM-52")
@pytest.mark.parametrize(("stock", "result"), [(3, "available"), (2, "partially_available")])
async def test_exactly_the_requested_quantity_is_enough(
    db: Session, make_user: MakeUser, make_client: MakeClient, stock: int, result: str
) -> None:
    event, _ = planning_event(db, make_user)
    equipment_type = new_type()
    entry(db, equipment_type, stock)
    requirement(db, event, equipment_type, quantity=3)

    async with make_client(make_user("tech_support")) as client:
        response = await client.get(url(event))

    assert response.json()[0]["result"] == result


@pytest.mark.story("SCRUM-52")
async def test_a_removed_requirement_is_not_checked(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = planning_event(db, make_user)
    requirement(db, event, new_type(), removed_at=datetime.now(UTC))

    async with make_client(make_user("tech_support")) as client:
        response = await client.get(url(event))

    assert response.status_code == 200
    assert response.json() == []


# --------------------------------------------------------------------------- AC2


@pytest.mark.story("SCRUM-52")
async def test_reserved_quantity_is_asked_for_the_event_window_and_subtracted(
    db: Session, make_user: MakeUser, make_client: MakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The repository is stood in for to prove the call site on its own: the window and
    # event id go in, and the answer is subtracted. SCRUM-53's tests cover the real query.
    event, _ = planning_event(db, make_user)
    equipment_type = new_type()
    entry(db, equipment_type, 5)
    requirement(db, event, equipment_type, quantity=3)
    calls: list[tuple[Any, ...]] = []

    def reserved(*args: Any, **kwargs: Any) -> int:
        calls.append((*args[1:], kwargs))
        return 4

    monkeypatch.setattr(catalogue_repo, "reserved_quantity", reserved)
    async with make_client(make_user("tech_support")) as client:
        response = await client.get(url(event))

    [checked] = response.json()
    assert (checked["reserved"], checked["available"], checked["result"]) == (
        4,
        1,
        "partially_available",
    )
    assert calls == [
        (equipment_type, event.start_at, event.end_at, {"excluding_event_id": event.id})
    ]


@pytest.mark.story("SCRUM-52")
def test_nothing_is_reserved_for_a_type_without_reservations(db: Session) -> None:
    now = datetime.now(UTC)
    assert catalogue_repo.reserved_quantity(db, new_type(), now, now, uuid.uuid4()) == 0


# --------------------------------------------------------------------------- AC3


@pytest.mark.story("SCRUM-52")
@pytest.mark.parametrize("status", [s for s in OPERATIONAL_STATUSES if s != IN_SERVICE_STATUS])
async def test_equipment_out_of_service_is_not_counted(
    db: Session, make_user: MakeUser, make_client: MakeClient, status: str
) -> None:
    event, _ = planning_event(db, make_user)
    equipment_type = new_type()
    entry(db, equipment_type, 2)
    entry(db, equipment_type, 10, status=status)
    requirement(db, event, equipment_type, quantity=3)

    async with make_client(make_user("tech_support")) as client:
        response = await client.get(url(event))

    assert (response.json()[0]["stock"], response.json()[0]["result"]) == (
        2,
        "partially_available",
    )


@pytest.mark.story("SCRUM-52")
async def test_an_inactive_entry_is_not_counted(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = planning_event(db, make_user)
    equipment_type = new_type()
    entry(db, equipment_type, 10, is_active=False)
    requirement(db, event, equipment_type, quantity=1)

    async with make_client(make_user("tech_support")) as client:
        response = await client.get(url(event))

    assert (response.json()[0]["stock"], response.json()[0]["result"]) == (0, "unavailable")


@pytest.mark.story("SCRUM-52")
async def test_entries_of_one_type_are_summed_across_locations(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = planning_event(db, make_user)
    equipment_type = new_type()
    entry(db, equipment_type, 2)
    entry(db, equipment_type, 3)
    entry(db, new_type(), 50)
    requirement(db, event, equipment_type, quantity=5)

    async with make_client(make_user("tech_support")) as client:
        response = await client.get(url(event))

    assert (response.json()[0]["stock"], response.json()[0]["result"]) == (5, "available")


# --------------------------------------------------------------------------- AC5


@pytest.mark.story("SCRUM-52")
async def test_the_assigned_coordinator_may_check(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, coordinator = planning_event(db, make_user)
    requirement(db, event, new_type())

    async with make_client(coordinator) as client:
        response = await client.get(url(event))

    assert response.status_code == 200, response.text
    assert len(response.json()) == 1


@pytest.mark.story("SCRUM-52")
async def test_a_different_coordinator_may_not_check(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = planning_event(db, make_user)

    async with make_client(make_user("coordinator")) as client:
        response = await client.get(url(event))

    assert response.status_code == 403


@pytest.mark.story("SCRUM-52")
@pytest.mark.parametrize("role", OTHER_ROLES)
async def test_other_roles_may_not_check(
    db: Session, make_user: MakeUser, make_client: MakeClient, role: str
) -> None:
    event, _ = planning_event(db, make_user)

    async with make_client(make_user(role)) as client:
        response = await client.get(url(event))

    assert response.status_code == 403


@pytest.mark.story("SCRUM-52")
async def test_the_owning_organiser_may_not_check(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = planning_event(db, make_user)
    organiser = db.get(User, event.organiser_id)

    async with make_client(organiser) as client:
        response = await client.get(url(event))

    assert response.status_code == 403


@pytest.mark.story("SCRUM-52")
async def test_anonymous_may_not_check(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = planning_event(db, make_user)

    async with make_client(None) as client:
        response = await client.get(url(event))

    assert response.status_code == 401


@pytest.mark.story("SCRUM-52")
async def test_a_missing_event_is_not_found(make_user: MakeUser, make_client: MakeClient) -> None:
    async with make_client(make_user("tech_support")) as client:
        response = await client.get(f"/api/event-requests/{uuid.uuid4()}/equipment-availability")

    assert response.status_code == 404


@pytest.mark.story("SCRUM-52")
@pytest.mark.parametrize("status", [s for s in EventStatus if s is not EventStatus.APPROVED])
async def test_an_event_not_in_planning_is_a_conflict(
    db: Session, make_user: MakeUser, make_client: MakeClient, status: EventStatus
) -> None:
    event, _ = planning_event(db, make_user)
    event.status = status
    db.flush()

    async with make_client(make_user("tech_support")) as client:
        response = await client.get(url(event))

    assert response.status_code == 409


# --------------------------------------------------------------------------- AC6


def snapshot(db: Session) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    db.expire_all()
    equipment = db.scalars(select(Equipment).order_by(Equipment.id))
    requirements = db.scalars(
        select(EventEquipmentRequirement).order_by(EventEquipmentRequirement.id)
    )
    return (
        [(e.id, e.total_quantity, e.operational_status, e.is_active) for e in equipment],
        [(r.id, r.quantity, r.review_status, r.removed_at, r.updated_at) for r in requirements],
    )


@pytest.mark.story("SCRUM-52")
async def test_checking_changes_no_equipment_or_requirement(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = planning_event(db, make_user)
    equipment_type = new_type()
    entry(db, equipment_type, 2)
    requirement(db, event, equipment_type, quantity=2)
    before = snapshot(db)

    async with make_client(make_user("tech_support")) as client:
        response = await client.get(url(event))

    assert response.json()[0]["result"] == "available"
    assert snapshot(db) == before
