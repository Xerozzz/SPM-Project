"""SCRUM-53: what SCRUM-52's availability check counts as reserved, from real rows.

Reservations are inserted through the model rather than a route, because the reserve
route arrives separately; these tests prove the query that counts them. Every test
invents its own equipment type, so rows from other tests never leak into the sums.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from models.equipment_reservation import EquipmentReservation
from models.event_request import EventRequest
from repositories import equipment as catalogue_repo
from tests.integration.test_equipment_availability import entry, new_type, url
from tests.integration.test_equipment_requirements import planning_event
from tests.integration.test_review_equipment_requirements import requirement
from tests.integration.test_submit_event_request import MakeClient, MakeUser


def window() -> tuple[datetime, datetime]:
    start = datetime.now(UTC) + timedelta(days=7)
    return start, start + timedelta(hours=3)


def reserve(
    db: Session,
    make_user: MakeUser,
    holder: EventRequest,
    equipment_type: str,
    quantity: int,
    starts_at: datetime,
    ends_at: datetime,
    released_at: datetime | None = None,
) -> EquipmentReservation:
    """A reservation held by `holder`, against a requirement of its own for the type."""
    held_for = requirement(db, holder, equipment_type, quantity=quantity)
    row = EquipmentReservation(
        requirement_id=held_for.id,
        event_request_id=holder.id,
        equipment_type=equipment_type,
        quantity=quantity,
        starts_at=starts_at,
        ends_at=ends_at,
        created_by_id=make_user("tech_support").id,
        released_at=released_at,
    )
    db.add(row)
    db.flush()
    return row


def other_event(db: Session, make_user: MakeUser) -> EventRequest:
    event, _ = planning_event(db, make_user)
    return event


@pytest.mark.story("SCRUM-53")
def test_a_reservation_overlapping_the_window_counts(db: Session, make_user: MakeUser) -> None:
    start, end = window()
    equipment_type = new_type()
    held = reserve(
        db,
        make_user,
        other_event(db, make_user),
        equipment_type,
        2,
        start + timedelta(hours=1),
        end + timedelta(hours=1),
    )
    asking = other_event(db, make_user)

    assert held.created_at.tzinfo is not None
    assert catalogue_repo.reserved_quantity(db, equipment_type, start, end, asking.id) == 2


@pytest.mark.story("SCRUM-53")
def test_back_to_back_reservations_do_not_count(db: Session, make_user: MakeUser) -> None:
    # Half-open windows: ending exactly at the start, or starting exactly at the end,
    # shares no instant with [start, end).
    start, end = window()
    equipment_type = new_type()
    before, after = other_event(db, make_user), other_event(db, make_user)
    reserve(db, make_user, before, equipment_type, 1, start - timedelta(hours=2), start)
    reserve(db, make_user, after, equipment_type, 1, end, end + timedelta(hours=2))
    asking = other_event(db, make_user)

    assert catalogue_repo.reserved_quantity(db, equipment_type, start, end, asking.id) == 0


@pytest.mark.story("SCRUM-53")
def test_a_released_reservation_does_not_count(db: Session, make_user: MakeUser) -> None:
    start, end = window()
    equipment_type = new_type()
    reserve(
        db,
        make_user,
        other_event(db, make_user),
        equipment_type,
        3,
        start,
        end,
        released_at=datetime.now(UTC),
    )
    asking = other_event(db, make_user)

    assert catalogue_repo.reserved_quantity(db, equipment_type, start, end, asking.id) == 0


@pytest.mark.story("SCRUM-53")
def test_the_asking_events_own_reservation_does_not_count(db: Session, make_user: MakeUser) -> None:
    start, end = window()
    equipment_type = new_type()
    asking = other_event(db, make_user)
    reserve(db, make_user, asking, equipment_type, 3, start, end)

    assert catalogue_repo.reserved_quantity(db, equipment_type, start, end, asking.id) == 0


@pytest.mark.story("SCRUM-53")
def test_a_reservation_of_another_type_does_not_count(db: Session, make_user: MakeUser) -> None:
    start, end = window()
    equipment_type = new_type()
    reserve(db, make_user, other_event(db, make_user), new_type(), 3, start, end)
    asking = other_event(db, make_user)

    assert catalogue_repo.reserved_quantity(db, equipment_type, start, end, asking.id) == 0


@pytest.mark.story("SCRUM-53")
def test_overlapping_reservations_are_summed(db: Session, make_user: MakeUser) -> None:
    start, end = window()
    equipment_type = new_type()
    reserve(db, make_user, other_event(db, make_user), equipment_type, 2, start, end)
    reserve(
        db,
        make_user,
        other_event(db, make_user),
        equipment_type,
        3,
        start - timedelta(hours=1),
        start + timedelta(minutes=1),
    )
    reserve(
        db,
        make_user,
        other_event(db, make_user),
        equipment_type,
        4,
        end - timedelta(minutes=1),
        end + timedelta(hours=1),
    )
    asking = other_event(db, make_user)

    assert catalogue_repo.reserved_quantity(db, equipment_type, start, end, asking.id) == 9


@pytest.mark.story("SCRUM-53")
async def test_the_availability_check_subtracts_a_real_reservation(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = planning_event(db, make_user)
    assert event.start_at is not None and event.end_at is not None
    equipment_type = new_type()
    entry(db, equipment_type, 5)
    requirement(db, event, equipment_type, quantity=3)
    reserve(
        db, make_user, other_event(db, make_user), equipment_type, 4, event.start_at, event.end_at
    )

    async with make_client(make_user("tech_support")) as client:
        response = await client.get(url(event))

    assert response.status_code == 200, response.text
    [checked] = response.json()
    assert {k: checked[k] for k in ("stock", "reserved", "available", "result")} == {
        "stock": 5,
        "reserved": 4,
        "available": 1,
        "result": "partially_available",
    }
