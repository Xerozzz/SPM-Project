"""SCRUM-53 AC6 and ADR-0033: a reservation stays visible, and is flagged when its line changes.

Against real PostgreSQL, reusing SCRUM-43's planning event and SCRUM-44's requirement
helper. Reservations are inserted directly rather than through the reserve route, because
what is under test is what happens to them afterwards, not how they were made.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from models.equipment_reservation import EquipmentReservation
from models.event_equipment_requirement import EventEquipmentRequirement
from models.event_request import EventRequest
from models.user import User
from tests.integration.test_equipment_requirements import planning_event, url
from tests.integration.test_review_equipment_requirements import REVIEW_LIST, requirement, rows_for
from tests.integration.test_submit_event_request import MakeClient, MakeUser


def held(
    db: Session,
    event: EventRequest,
    row: EventEquipmentRequirement,
    quantity: int,
    by: User,
    *,
    released: bool = False,
) -> EquipmentReservation:
    assert event.start_at is not None and event.end_at is not None
    now = datetime.now(UTC)
    reservation = EquipmentReservation(
        requirement_id=row.id,
        event_request_id=event.id,
        equipment_type=row.equipment_type,
        quantity=quantity,
        starts_at=event.start_at,
        ends_at=event.end_at,
        created_by_id=by.id,
        created_at=now,
        released_at=now if released else None,
    )
    db.add(reservation)
    db.flush()
    return reservation


def flags(db: Session, *reservations: EquipmentReservation) -> list[datetime | None]:
    db.expire_all()
    return [
        db.scalars(
            select(EquipmentReservation.flagged_at).where(EquipmentReservation.id == r.id)
        ).one()
        for r in reservations
    ]


def summary(data: dict[str, Any]) -> tuple[Any, ...]:
    return (data["reserved_quantity"], data["reservation_state"], data["has_flagged_reservation"])


@pytest.mark.story("SCRUM-53")
async def test_changing_a_reserved_requirement_flags_its_reservations(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, coordinator = planning_event(db, make_user)
    row = requirement(db, event, quantity=3)
    tech = make_user("tech_support")
    first, second = held(db, event, row, 1, tech), held(db, event, row, 2, tech)

    async with make_client(coordinator) as client:
        response = await client.patch(url(event, f"/{row.id}"), json={"quantity": 5})

    assert response.status_code == 200, response.text
    assert summary(response.json()) == (3, "partially_reserved", True)
    first_flag, second_flag = flags(db, first, second)
    assert first_flag is not None and first_flag == second_flag
    assert first_flag.tzinfo is not None


@pytest.mark.story("SCRUM-53")
async def test_removing_a_reserved_requirement_flags_but_keeps_its_reservation(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, coordinator = planning_event(db, make_user)
    row = requirement(db, event, quantity=2)
    reservation = held(db, event, row, 2, make_user("tech_support"))

    async with make_client(coordinator) as client:
        response = await client.delete(url(event, f"/{row.id}"))

    assert response.status_code == 200, response.text
    assert summary(response.json()) == (2, "reserved", True)
    [flag] = flags(db, reservation)
    assert flag is not None
    db.refresh(reservation)
    assert reservation.released_at is None


@pytest.mark.story("SCRUM-53")
async def test_a_change_with_nothing_reserved_flags_nothing(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, coordinator = planning_event(db, make_user)
    row = requirement(db, event, quantity=2)
    # Another line on the same event holds stock; changing this one must not touch it.
    other = requirement(db, event, "Microphone", quantity=1)
    untouched = held(db, event, other, 1, make_user("tech_support"))

    async with make_client(coordinator) as client:
        response = await client.patch(url(event, f"/{row.id}"), json={"quantity": 4})

    assert response.status_code == 200, response.text
    assert summary(response.json()) == (0, "not_reserved", False)
    assert flags(db, untouched) == [None]


@pytest.mark.story("SCRUM-53")
async def test_a_released_reservation_is_not_flagged_or_counted(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, coordinator = planning_event(db, make_user)
    row = requirement(db, event, quantity=3)
    tech = make_user("tech_support")
    released = held(db, event, row, 2, tech, released=True)
    live = held(db, event, row, 1, tech)

    async with make_client(coordinator) as client:
        response = await client.patch(url(event, f"/{row.id}"), json={"quantity": 4})

    assert summary(response.json()) == (1, "partially_reserved", True)
    released_flag, live_flag = flags(db, released, live)
    assert released_flag is None
    assert live_flag is not None


@pytest.mark.story("SCRUM-53")
async def test_a_second_change_keeps_the_first_flag_time(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, coordinator = planning_event(db, make_user)
    row = requirement(db, event, quantity=3)
    reservation = held(db, event, row, 1, make_user("tech_support"))
    reservation.flagged_at = datetime.now(UTC) - timedelta(days=1)
    db.flush()
    earlier = reservation.flagged_at

    async with make_client(coordinator) as client:
        await client.patch(url(event, f"/{row.id}"), json={"quantity": 4})

    assert flags(db, reservation) == [earlier]


@pytest.mark.story("SCRUM-53")
async def test_the_assigned_coordinator_sees_what_is_reserved_on_the_event(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, coordinator = planning_event(db, make_user)
    partly = requirement(db, event, quantity=3)
    fully = requirement(db, event, "Microphone", quantity=1)
    unreserved = requirement(db, event, "Speaker", quantity=2)
    tech = make_user("tech_support")
    held(db, event, partly, 2, tech)
    held(db, event, fully, 1, tech)

    async with make_client(coordinator) as client:
        response = await client.get(url(event))

    assert response.status_code == 200, response.text
    by_id = {data["id"]: summary(data) for data in response.json()}
    assert by_id == {
        str(partly.id): (2, "partially_reserved", False),
        str(fully.id): (1, "reserved", False),
        str(unreserved.id): (0, "not_reserved", False),
    }


@pytest.mark.story("SCRUM-53")
async def test_technical_support_see_reservations_and_flags_in_the_review_list(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = planning_event(db, make_user)
    flagged = requirement(db, event, quantity=2)
    unreserved = requirement(db, event, "Microphone", quantity=1)
    tech = make_user("tech_support")
    reservation = held(db, event, flagged, 1, tech)
    reservation.flagged_at = datetime.now(UTC)
    db.flush()

    async with make_client(tech) as client:
        response = await client.get(REVIEW_LIST)

    assert response.status_code == 200, response.text
    by_id = {data["id"]: summary(data) for data in rows_for(response.json(), event)}
    assert by_id == {
        str(flagged.id): (1, "partially_reserved", True),
        str(unreserved.id): (0, "not_reserved", False),
    }
