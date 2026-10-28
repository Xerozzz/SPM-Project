"""SCRUM-53: Technical Support Staff reserve equipment for an event.

Against real PostgreSQL, reusing SCRUM-43's planning event, SCRUM-44's requirement helper
and SCRUM-52's catalogue helpers. Every test invents its own equipment type, so stock
seeded elsewhere never leaks into the sums asserted here.
"""

import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.database import SessionLocal
from core.security import hash_password
from domain.equipment import OPERATIONAL_STATUSES
from domain.equipment_availability import IN_SERVICE_STATUS
from domain.event_status import EventStatus
from models.equipment import Equipment
from models.equipment_reservation import EquipmentReservation
from models.event_equipment_requirement import EventEquipmentRequirement
from models.event_request import EventRequest
from models.notification import Notification
from models.organisation import Organisation
from models.user import User
from services import equipment_reservations as service
from tests.integration.test_equipment_availability import entry, new_type
from tests.integration.test_equipment_availability import url as availability_url
from tests.integration.test_equipment_requirements import planning_event
from tests.integration.test_review_equipment_requirements import requirement, stock
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_submit_venue_booking import approved_event

OTHER_ROLES = ["organiser", "coordinator", "coordinator_lead", "venue_staff", "attendee"]


def url(event: EventRequest, row: EventEquipmentRequirement) -> str:
    return f"/api/event-requests/{event.id}/equipment-requirements/{row.id}/reserve"


async def reserve(
    client: httpx.AsyncClient,
    event: EventRequest,
    row: EventEquipmentRequirement,
    quantity: int | None = None,
) -> httpx.Response:
    body = None if quantity is None else {"quantity": quantity}
    return await client.post(url(event, row), json=body)


def reservations(db: Session) -> list[EquipmentReservation]:
    db.expire_all()
    return list(db.scalars(select(EquipmentReservation).order_by(EquipmentReservation.created_at)))


def outcome(response: httpx.Response) -> tuple[Any, ...]:
    data = response.json()
    return (data["reserved_now"], data["total_reserved"], data["outstanding"], data["state"])


# ------------------------------------------------------------- AC1, AC2 and AC7


@pytest.mark.story("SCRUM-53")
async def test_an_available_quantity_is_reserved_in_full(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = planning_event(db, make_user)
    equipment_type = new_type()
    entry(db, equipment_type, 5)
    row = requirement(db, event, equipment_type, quantity=3)
    tech = make_user("tech_support")

    async with make_client(tech) as client:
        response = await reserve(client, event, row)

    assert response.status_code == 201, response.text
    assert outcome(response) == (3, 3, 0, "reserved")
    data = response.json()
    assert data["equipment_type"] == equipment_type
    assert data["requirement_id"] == str(row.id)
    assert datetime.fromisoformat(data["event_start_at"]) == event.start_at
    assert datetime.fromisoformat(data["event_end_at"]) == event.end_at
    [stored] = reservations(db)
    assert (stored.requirement_id, stored.event_request_id, stored.equipment_type) == (
        row.id,
        event.id,
        equipment_type,
    )
    assert (stored.quantity, stored.starts_at, stored.ends_at) == (3, event.start_at, event.end_at)
    assert stored.created_by_id == tech.id
    assert (stored.released_at, stored.flagged_at) == (None, None)


@pytest.mark.story("SCRUM-53")
async def test_only_what_is_free_is_reserved_by_default(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = planning_event(db, make_user)
    equipment_type = new_type()
    entry(db, equipment_type, 1)
    row = requirement(db, event, equipment_type, quantity=3)

    async with make_client(make_user("tech_support")) as client:
        response = await reserve(client, event, row)

    assert response.status_code == 201, response.text
    assert outcome(response) == (1, 1, 2, "partially_reserved")


@pytest.mark.story("SCRUM-53")
async def test_an_explicit_quantity_is_reserved_exactly(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = planning_event(db, make_user)
    equipment_type = new_type()
    entry(db, equipment_type, 5)
    row = requirement(db, event, equipment_type, quantity=3)

    async with make_client(make_user("tech_support")) as client:
        response = await reserve(client, event, row, quantity=1)

    assert outcome(response) == (1, 1, 2, "partially_reserved")


@pytest.mark.story("SCRUM-53")
async def test_re_reserving_fills_only_what_is_outstanding(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = planning_event(db, make_user)
    equipment_type = new_type()
    entry(db, equipment_type, 10)
    row = requirement(db, event, equipment_type, quantity=3)

    async with make_client(make_user("tech_support")) as client:
        first = await reserve(client, event, row, quantity=1)
        second = await reserve(client, event, row)
        third = await reserve(client, event, row)

    assert outcome(first) == (1, 1, 2, "partially_reserved")
    assert outcome(second) == (2, 3, 0, "reserved")
    assert third.status_code == 409
    assert third.json()["detail"] == "nothing_outstanding"
    assert [r.quantity for r in reservations(db)] == [1, 2]


# --------------------------------------------------------------------------- AC3


@pytest.mark.story("SCRUM-53")
async def test_an_explicit_quantity_above_what_is_free_is_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = planning_event(db, make_user)
    equipment_type = new_type()
    entry(db, equipment_type, 2)
    row = requirement(db, event, equipment_type, quantity=3)

    async with make_client(make_user("tech_support")) as client:
        response = await reserve(client, event, row, quantity=3)

    assert response.status_code == 409
    assert response.json()["detail"] == "above_free"
    assert reservations(db) == []


@pytest.mark.story("SCRUM-53")
async def test_an_explicit_quantity_above_what_is_needed_is_invalid(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = planning_event(db, make_user)
    equipment_type = new_type()
    entry(db, equipment_type, 10)
    row = requirement(db, event, equipment_type, quantity=3)

    async with make_client(make_user("tech_support")) as client:
        response = await reserve(client, event, row, quantity=4)

    assert response.status_code == 422
    assert response.json()["detail"] == "above_outstanding"
    assert reservations(db) == []


@pytest.mark.story("SCRUM-53")
@pytest.mark.parametrize("quantity", [0, -1, True, "2"])
async def test_a_quantity_that_is_not_a_positive_number_is_invalid(
    db: Session, make_user: MakeUser, make_client: MakeClient, quantity: object
) -> None:
    event, _ = planning_event(db, make_user)
    equipment_type = new_type()
    entry(db, equipment_type, 10)
    row = requirement(db, event, equipment_type, quantity=3)

    async with make_client(make_user("tech_support")) as client:
        response = await client.post(url(event, row), json={"quantity": quantity})

    assert response.status_code == 422
    assert reservations(db) == []


@pytest.mark.story("SCRUM-53")
async def test_nothing_free_is_refused_with_the_reason(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = planning_event(db, make_user)
    row = requirement(db, event, new_type(), quantity=1)

    async with make_client(make_user("tech_support")) as client:
        response = await reserve(client, event, row)

    assert response.status_code == 409
    assert response.json()["detail"] == "nothing_free"
    assert reservations(db) == []


# --------------------------------------------------------------------------- AC4


@pytest.mark.story("SCRUM-53")
@pytest.mark.parametrize("status", [s for s in OPERATIONAL_STATUSES if s != IN_SERVICE_STATUS])
async def test_equipment_out_of_service_is_not_reserved(
    db: Session, make_user: MakeUser, make_client: MakeClient, status: str
) -> None:
    event, _ = planning_event(db, make_user)
    equipment_type = new_type()
    entry(db, equipment_type, 1)
    entry(db, equipment_type, 10, status=status)
    row = requirement(db, event, equipment_type, quantity=3)

    async with make_client(make_user("tech_support")) as client:
        response = await reserve(client, event, row)

    assert outcome(response) == (1, 1, 2, "partially_reserved")


@pytest.mark.story("SCRUM-53")
async def test_an_inactive_entry_is_not_reserved(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = planning_event(db, make_user)
    equipment_type = new_type()
    entry(db, equipment_type, 10, is_active=False)
    row = requirement(db, event, equipment_type, quantity=1)

    async with make_client(make_user("tech_support")) as client:
        response = await reserve(client, event, row)

    assert response.status_code == 409
    assert response.json()["detail"] == "nothing_free"


# --------------------------------------------------------------------------- AC5


@pytest.mark.story("SCRUM-53")
async def test_overlapping_events_reduce_each_others_availability(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # Both planning events start thirty days out and last four hours, so they overlap.
    first, _ = planning_event(db, make_user)
    second, _ = planning_event(db, make_user)
    equipment_type = new_type()
    entry(db, equipment_type, 3)
    first_row = requirement(db, first, equipment_type, quantity=2)
    second_row = requirement(db, second, equipment_type, quantity=3)

    async with make_client(make_user("tech_support")) as client:
        await reserve(client, first, first_row)
        checked = await client.get(availability_url(second))
        reserved = await reserve(client, second, second_row)
        checked_first = await client.get(availability_url(first))

    [row] = checked.json()
    assert (row["stock"], row["reserved"], row["available"], row["result"]) == (
        3,
        2,
        1,
        "partially_available",
    )
    assert outcome(reserved) == (1, 1, 2, "partially_reserved")
    # The first event's own reservation is not counted against it, but the second's is.
    assert checked_first.json()[0]["reserved"] == 1


@pytest.mark.story("SCRUM-53")
async def test_back_to_back_events_do_not_conflict(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    start = datetime.now(UTC).replace(microsecond=0) + timedelta(days=40)
    first, _ = planning_event(db, make_user, start_at=start, end_at=start + timedelta(hours=2))
    second, _ = planning_event(
        db, make_user, start_at=start + timedelta(hours=2), end_at=start + timedelta(hours=4)
    )
    equipment_type = new_type()
    entry(db, equipment_type, 2)
    first_row = requirement(db, first, equipment_type, quantity=2)
    second_row = requirement(db, second, equipment_type, quantity=2)

    async with make_client(make_user("tech_support")) as client:
        await reserve(client, first, first_row)
        response = await reserve(client, second, second_row)

    assert outcome(response) == (2, 2, 0, "reserved")


@pytest.mark.story("SCRUM-53")
async def test_reserving_changes_no_catalogue_stock(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = planning_event(db, make_user)
    equipment_type = new_type()
    entry(db, equipment_type, 5)
    row = requirement(db, event, equipment_type, quantity=3)
    before = stock(db)

    async with make_client(make_user("tech_support")) as client:
        response = await reserve(client, event, row)

    assert response.status_code == 201
    db.expire_all()
    assert stock(db) == before


# --------------------------------------------------------- not found and conflict


@pytest.mark.story("SCRUM-53")
async def test_a_missing_requirement_is_not_found(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = planning_event(db, make_user)

    async with make_client(make_user("tech_support")) as client:
        response = await client.post(
            f"/api/event-requests/{event.id}/equipment-requirements/{uuid.uuid4()}/reserve"
        )

    assert response.status_code == 404


@pytest.mark.story("SCRUM-53")
async def test_a_removed_requirement_is_not_found(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = planning_event(db, make_user)
    equipment_type = new_type()
    entry(db, equipment_type, 5)
    row = requirement(db, event, equipment_type, removed_at=datetime.now(UTC))

    async with make_client(make_user("tech_support")) as client:
        response = await reserve(client, event, row)

    assert response.status_code == 404


@pytest.mark.story("SCRUM-53")
async def test_a_requirement_of_another_event_is_not_found(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = planning_event(db, make_user)
    other, _ = planning_event(db, make_user)
    equipment_type = new_type()
    entry(db, equipment_type, 5)
    row = requirement(db, other, equipment_type)

    async with make_client(make_user("tech_support")) as client:
        response = await reserve(client, event, row)

    assert response.status_code == 404
    assert reservations(db) == []


@pytest.mark.story("SCRUM-53")
@pytest.mark.parametrize("status", [s for s in EventStatus if s is not EventStatus.APPROVED])
async def test_an_event_not_in_planning_is_a_conflict(
    db: Session, make_user: MakeUser, make_client: MakeClient, status: EventStatus
) -> None:
    event, _ = planning_event(db, make_user)
    equipment_type = new_type()
    entry(db, equipment_type, 5)
    row = requirement(db, event, equipment_type)
    event.status = status
    db.flush()

    async with make_client(make_user("tech_support")) as client:
        response = await reserve(client, event, row)

    assert response.status_code == 409
    assert response.json()["detail"] == "Event is not in planning"


@pytest.mark.story("SCRUM-53")
@pytest.mark.parametrize("missing", ["start_at", "end_at"])
async def test_an_event_without_a_window_is_a_conflict(
    db: Session, make_user: MakeUser, make_client: MakeClient, missing: str
) -> None:
    event, _ = planning_event(db, make_user, **{missing: None})
    equipment_type = new_type()
    entry(db, equipment_type, 5)
    row = requirement(db, event, equipment_type)

    async with make_client(make_user("tech_support")) as client:
        response = await reserve(client, event, row)

    assert response.status_code == 409
    assert response.json()["detail"] == "Event has no start or end time"


# ------------------------------------------------------------------ authorisation


@pytest.mark.story("SCRUM-53")
@pytest.mark.parametrize("role", OTHER_ROLES)
async def test_other_roles_may_not_reserve(
    db: Session, make_user: MakeUser, make_client: MakeClient, role: str
) -> None:
    event, _ = planning_event(db, make_user)
    equipment_type = new_type()
    entry(db, equipment_type, 5)
    row = requirement(db, event, equipment_type)

    async with make_client(make_user(role)) as client:
        response = await reserve(client, event, row)

    assert response.status_code == 403
    assert reservations(db) == []


@pytest.mark.story("SCRUM-53")
async def test_the_assigned_coordinator_may_not_reserve(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, coordinator = planning_event(db, make_user)
    equipment_type = new_type()
    entry(db, equipment_type, 5)
    row = requirement(db, event, equipment_type)

    async with make_client(coordinator) as client:
        response = await reserve(client, event, row)

    assert response.status_code == 403


@pytest.mark.story("SCRUM-53")
async def test_anonymous_may_not_reserve(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = planning_event(db, make_user)
    row = requirement(db, event, new_type())

    async with make_client(None) as client:
        response = await reserve(client, event, row)

    assert response.status_code == 401


# ----------------------------------------------------------- AC3: concurrency
#
# These need two real transactions racing, which the rolled-back `db` fixture cannot
# express, so they commit their own data and clean it up (as SCRUM-74's race test does).


@dataclass(frozen=True)
class _Committed:
    """Everything one race commits, so it can be deleted afterwards."""

    equipment_type: str
    requirement_ids: list[uuid.UUID]
    event_ids: list[uuid.UUID]
    equipment_id: uuid.UUID
    user_id: uuid.UUID
    organisation_id: uuid.UUID


def _committed_requirements(count: int, in_service: int) -> _Committed:
    """Commit `count` overlapping planning events, each needing two of one new type."""
    session = SessionLocal()
    try:
        organisation = Organisation(name=f"Race organisation {uuid.uuid4()}")
        session.add(organisation)
        session.flush()
        user = User(
            email=f"{uuid.uuid4()}@example.com",
            password_hash=hash_password("password123"),
            roles=["coordinator"],
            organisation_id=organisation.id,
        )
        session.add(user)
        session.flush()
        equipment_type = new_type()
        stocked = entry(session, equipment_type, in_service)
        start = datetime.now(UTC).replace(microsecond=0) + timedelta(days=30)
        events = [
            approved_event(session, user, user, start_at=start, end_at=start + timedelta(hours=4))
            for _ in range(count)
        ]
        rows = [requirement(session, event, equipment_type, quantity=2) for event in events]
        session.commit()
        return _Committed(
            equipment_type=equipment_type,
            requirement_ids=[r.id for r in rows],
            event_ids=[e.id for e in events],
            equipment_id=stocked.id,
            user_id=user.id,
            organisation_id=organisation.id,
        )
    finally:
        session.close()


def _delete_committed(committed: _Committed) -> None:
    """Delete children before parents, flushing between levels for the foreign keys.

    SCRUM-125 stages a notification per reservation, so the inbox rows go before the
    reservations they point at.
    """
    session = SessionLocal()
    try:
        held = select(EquipmentReservation).where(
            EquipmentReservation.equipment_type == committed.equipment_type
        )
        inbox = select(Notification).where(Notification.event_request_id.in_(committed.event_ids))
        levels: list[list[object]] = [
            list(session.scalars(inbox)),
            list(session.scalars(held)),
            [session.get(EventEquipmentRequirement, i) for i in committed.requirement_ids],
            [session.get(EventRequest, i) for i in committed.event_ids],
            [session.get(Equipment, committed.equipment_id)],
            [session.get(User, committed.user_id)],
            [session.get(Organisation, committed.organisation_id)],
        ]
        for rows in levels:
            for row in rows:
                session.delete(row)
            session.flush()
        session.commit()
    finally:
        session.close()


def _race(committed: _Committed, quantity: int) -> tuple[list[str], int]:
    """Reserve for each requirement on its own thread and session, released together."""
    start_together = threading.Barrier(len(committed.requirement_ids))
    outcomes: list[str] = []

    def reserve_once(event_id: uuid.UUID, requirement_id: uuid.UUID) -> None:
        session = SessionLocal()
        try:
            start_together.wait()
            service.reserve(
                session, event_id, requirement_id, quantity, committed.user_id, datetime.now(UTC)
            )
            outcomes.append("reserved")
        except service.ReservationRefusedError as exc:
            outcomes.append(exc.refusal.value)
        finally:
            session.close()

    pairs = zip(committed.event_ids, committed.requirement_ids, strict=True)
    threads = [threading.Thread(target=reserve_once, args=pair) for pair in pairs]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    session = SessionLocal()
    try:
        statement = select(func.coalesce(func.sum(EquipmentReservation.quantity), 0)).where(
            EquipmentReservation.equipment_type == committed.equipment_type
        )
        total = int(session.scalar(statement) or 0)
    finally:
        session.close()
    return outcomes, total


@pytest.mark.story("SCRUM-53")
@pytest.mark.parametrize("attempt", range(5))
def test_simultaneous_reservations_of_the_last_units_yield_exactly_one_success(
    attempt: int,
) -> None:
    """AC3: two Technical Support Staff each reserve two of a type with three in service,
    for two overlapping events, at the same instant. The catalogue row lock makes the
    second wait for the first to commit, then count again and find only one free, so it
    is refused (409 at the route) and the type is never over-committed (ADR-0038)."""
    del attempt  # the run number only exists to repeat the race
    committed = _committed_requirements(2, in_service=3)
    try:
        outcomes, total = _race(committed, quantity=2)

        assert sorted(outcomes) == ["above_free", "reserved"]
        assert total == 2
    finally:
        _delete_committed(committed)
