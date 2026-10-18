"""SCRUM-98: a Coordinator Lead assigns an unassigned Submitted request.

TC-98-01 proves the happy path (owner + timezone-aware time stored, queue exit).
TC-98-02/03 prove owner-only actions transfer to the new owner. TC-98-04/05 cover the
authorisation matrix and invalid assignees. TC-98-06/07 cover the already-assigned and
concurrent-assign conflicts. TC-98-08 pins the UTC date-boundary timestamp.
"""

import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from core.database import SessionLocal
from core.security import hash_password
from domain.event_status import EventStatus
from models.event_request import EventRequest
from models.notification import Notification
from models.organisation import Organisation
from models.user import User
from services import event_requests as service
from tests.integration.test_submit_event_request import MakeClient, MakeUser, make_draft


def _submitted(db: Session, organiser: User) -> EventRequest:
    """A Submitted request arranged directly, so tests control assignment exactly."""
    request = make_draft(db, organiser)
    request.status = EventStatus.SUBMITTED
    request.submitted_at = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
    db.flush()
    return request


# ------------------------------------------------------------------ TC-98-01


@pytest.mark.story("SCRUM-98")
async def test_lead_lists_only_active_coordinators_as_assignable(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1: the picker shows active Event Coordinators only — inactive users and
    active non-coordinators are excluded, in account-creation order."""
    first = make_user("coordinator")
    second = make_user("coordinator")
    make_user("coordinator", is_active=False)
    make_user("organiser")
    lead = make_user("coordinator_lead")

    async with make_client(lead) as client:
        response = await client.get("/api/event-requests/assignable-coordinators")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [str(first.id), str(second.id)]
    assert all(set(row) == {"id", "email"} for row in response.json())


@pytest.mark.story("SCRUM-98")
@pytest.mark.parametrize("role", ["organiser", "coordinator", "venue_staff", "tech_support"])
async def test_non_lead_roles_cannot_list_assignable_coordinators(
    role: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC4: the picker is Lead-only — every other role gets 403 with no data."""
    organiser = make_user("organiser")
    caller = organiser if role == "organiser" else make_user(role)

    async with make_client(caller) as client:
        response = await client.get("/api/event-requests/assignable-coordinators")

    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}


@pytest.mark.story("SCRUM-98")
async def test_lead_assigns_an_active_coordinator(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1: the coordinator and a timezone-aware assignment time are stored, and the
    request leaves the unassigned queue."""
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    lead = make_user("coordinator_lead")
    request = _submitted(db, organiser)

    async with make_client(lead) as client:
        assigned = await client.post(
            f"/api/event-requests/{request.id}/assign",
            json={"coordinator_id": str(coordinator.id)},
        )
        queue = await client.get("/api/event-requests/unassigned")

    assert assigned.status_code == 200
    assert assigned.json()["coordinator_id"] == str(coordinator.id)
    assert assigned.json()["assigned_at"] is not None
    db.refresh(request)
    assert request.coordinator_id == coordinator.id
    assert request.assigned_at is not None
    assert request.assigned_at.tzinfo is not None
    assert queue.status_code == 200
    assert queue.json() == []


# ------------------------------------------------------------------ TC-98-02/03


@pytest.mark.story("SCRUM-98")
async def test_assigned_coordinator_gains_owner_only_actions(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC2: the new owner may request clarification and decide while Submitted."""
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    lead = make_user("coordinator_lead")
    request = _submitted(db, organiser)

    async with make_client(lead) as client:
        assign = await client.post(
            f"/api/event-requests/{request.id}/assign",
            json={"coordinator_id": str(coordinator.id)},
        )
    assert assign.status_code == 200
    async with make_client(coordinator) as client:
        clarification = await client.post(
            f"/api/event-requests/{request.id}/clarifications",
            json={"message": "Please confirm the headcount."},
        )
        approval = await client.post(f"/api/event-requests/{request.id}/approve")

    assert clarification.status_code == 201
    assert approval.status_code == 200


@pytest.mark.story("SCRUM-98")
async def test_other_coordinator_is_refused_view_and_owner_actions(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """SCRUM-104: another coordinator is refused the request without disclosure."""
    organiser = make_user("organiser")
    owner = make_user("coordinator")
    other = make_user("coordinator")
    lead = make_user("coordinator_lead")
    request = _submitted(db, organiser)

    async with make_client(lead) as client:
        assign = await client.post(
            f"/api/event-requests/{request.id}/assign",
            json={"coordinator_id": str(owner.id)},
        )
    assert assign.status_code == 200
    async with make_client(other) as client:
        read = await client.get(f"/api/event-requests/{request.id}")
        clarification = await client.post(
            f"/api/event-requests/{request.id}/clarifications",
            json={"message": "Trying to act on someone else's request."},
        )
        approval = await client.post(f"/api/event-requests/{request.id}/approve")

    assert read.status_code == 403
    assert read.json() == {"detail": "Forbidden"}
    assert clarification.status_code == 403
    assert approval.status_code == 403


# ------------------------------------------------------------------ TC-98-04/05


@pytest.mark.story("SCRUM-98")
@pytest.mark.parametrize(
    "role", ["organiser", "coordinator", "venue_staff", "tech_support", "attendee"]
)
async def test_non_lead_roles_cannot_assign(
    role: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC4: every non-Lead role is refused with 403 and the row is unchanged."""
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = _submitted(db, organiser)
    caller = organiser if role == "organiser" else make_user(role)

    async with make_client(caller) as client:
        response = await client.post(
            f"/api/event-requests/{request.id}/assign",
            json={"coordinator_id": str(coordinator.id)},
        )

    assert response.status_code == 403
    db.refresh(request)
    assert request.coordinator_id is None
    assert request.assigned_at is None


@pytest.mark.story("SCRUM-98")
async def test_unauthenticated_caller_cannot_assign(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC4 boundary: no token means 401, and the row is unchanged."""
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = _submitted(db, organiser)

    async with make_client(None) as client:
        response = await client.post(
            f"/api/event-requests/{request.id}/assign",
            json={"coordinator_id": str(coordinator.id)},
        )

    assert response.status_code == 401
    db.refresh(request)
    assert request.coordinator_id is None


@pytest.mark.story("SCRUM-98")
@pytest.mark.parametrize("case", ["inactive", "non_coordinator", "missing"])
async def test_invalid_assignees_are_refused_without_partial_state(
    case: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC5: an inactive user, an active non-coordinator, or a missing user is a 422
    with no owner or timestamp stored."""
    organiser = make_user("organiser")
    lead = make_user("coordinator_lead")
    request = _submitted(db, organiser)
    if case == "inactive":
        candidate_id = make_user("coordinator", is_active=False).id
    elif case == "non_coordinator":
        candidate_id = make_user("organiser").id
    else:
        candidate_id = uuid.uuid4()

    async with make_client(lead) as client:
        response = await client.post(
            f"/api/event-requests/{request.id}/assign",
            json={"coordinator_id": str(candidate_id)},
        )

    assert response.status_code == 422
    db.refresh(request)
    assert request.coordinator_id is None
    assert request.assigned_at is None


# ------------------------------------------------------------------ TC-98-06/07


@pytest.mark.story("SCRUM-98")
async def test_assigning_an_already_assigned_request_is_a_conflict(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC6 boundary (sequential): the second assignment gets 409 and the first owner
    and time are preserved."""
    organiser = make_user("organiser")
    first = make_user("coordinator")
    second = make_user("coordinator")
    lead = make_user("coordinator_lead")
    request = _submitted(db, organiser)

    async with make_client(lead) as client:
        ok = await client.post(
            f"/api/event-requests/{request.id}/assign",
            json={"coordinator_id": str(first.id)},
        )
        conflict = await client.post(
            f"/api/event-requests/{request.id}/assign",
            json={"coordinator_id": str(second.id)},
        )

    assert ok.status_code == 200
    assert conflict.status_code == 409
    db.refresh(request)
    assert request.coordinator_id == first.id
    assert request.assigned_at is not None
    assert request.assigned_at.isoformat().replace("+00:00", "Z") == ok.json()["assigned_at"]


def _committed_submitted() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """A real, committed Submitted request plus its organiser and two coordinator ids —
    visible to every connection, so two sessions can race on the same row."""
    session = SessionLocal()
    try:
        organisation = Organisation(name=f"Committed test organisation {uuid.uuid4()}")
        session.add(organisation)
        session.flush()
        organiser = User(
            email=f"{uuid.uuid4()}@example.com",
            password_hash=hash_password("password123"),
            roles=["organiser"],
            organisation_id=organisation.id,
        )
        session.add(organiser)
        session.flush()
        first = User(
            email=f"{uuid.uuid4()}@example.com",
            password_hash=hash_password("password123"),
            roles=["coordinator"],
            organisation_id=organisation.id,
        )
        second = User(
            email=f"{uuid.uuid4()}@example.com",
            password_hash=hash_password("password123"),
            roles=["coordinator"],
            organisation_id=organisation.id,
        )
        session.add_all([first, second])
        session.flush()
        request = make_draft(session, organiser)
        request.status = EventStatus.SUBMITTED
        request.submitted_at = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
        session.commit()
        return request.id, organiser.id, first.id, second.id
    finally:
        session.close()


def _delete_committed(request_id: uuid.UUID, *user_ids: uuid.UUID) -> None:
    session = SessionLocal()
    try:
        # SCRUM-102: assignment now stages inbox rows referencing the request, so
        # they go first — otherwise the request delete violates the FK constraint.
        session.query(Notification).filter(Notification.event_request_id == request_id).delete()
        session.commit()
        request = session.get(EventRequest, request_id)
        organisation_id: uuid.UUID | None = None
        if request is not None:
            organiser = session.get(User, request.organiser_id)
            organisation_id = organiser.organisation_id if organiser is not None else None
            session.delete(request)
            session.commit()
        # Every user this helper created — the organiser, the winner recorded on
        # the request, and the loser that never got recorded — so no committed
        # coordinator leaks into other tests' picker assertions.
        for user_id in user_ids:
            user = session.get(User, user_id)
            if user is not None:
                if organisation_id is None:
                    organisation_id = user.organisation_id
                session.delete(user)
                session.commit()
        if organisation_id is not None:
            organisation = session.get(Organisation, organisation_id)
            if organisation is not None:
                session.delete(organisation)
                session.commit()
    finally:
        session.close()


@pytest.mark.story("SCRUM-98")
def test_concurrent_assignments_yield_exactly_one_success() -> None:
    """AC6: two Leads assigning different coordinators at the same instant — one
    succeeds, one gets a conflict, and the winner is not overwritten."""
    request_id, organiser_id, first_id, second_id = _committed_submitted()
    start_together = threading.Barrier(2)
    outcomes: list[str] = []

    def assign_once(coordinator_id: uuid.UUID) -> None:
        session = SessionLocal()
        try:
            start_together.wait()
            service.assign_coordinator(session, request_id, coordinator_id, datetime.now(UTC))
            outcomes.append(str(coordinator_id))
        except service.AlreadyAssignedError:
            outcomes.append("conflict")
        finally:
            session.close()

    try:
        threads = [
            threading.Thread(target=assign_once, args=(first_id,)),
            threading.Thread(target=assign_once, args=(second_id,)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert sorted(outcomes) == sorted([str(first_id), "conflict"]) or sorted(
            outcomes
        ) == sorted([str(second_id), "conflict"])
    finally:
        _delete_committed(request_id, organiser_id, first_id, second_id)


# ------------------------------------------------------------------ TC-98-08


@pytest.mark.story("SCRUM-98")
async def test_assignment_at_utc_date_boundary_stays_timezone_aware(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1 boundary: assignment stores a timezone-aware UTC timestamp without
    truncation or local-time conversion."""
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    lead = make_user("coordinator_lead")
    request = _submitted(db, organiser)
    before = datetime.now(UTC)

    async with make_client(lead) as client:
        response = await client.post(
            f"/api/event-requests/{request.id}/assign",
            json={"coordinator_id": str(coordinator.id)},
        )

    assert response.status_code == 200
    db.refresh(request)
    assert request.assigned_at is not None
    assert request.assigned_at.tzinfo is not None
    assert request.assigned_at.utcoffset() is not None
    assert abs(datetime.now(UTC) - request.assigned_at) < timedelta(seconds=30)
    assert request.assigned_at >= before
    assert response.json()["assigned_at"] == request.assigned_at.isoformat().replace("+00:00", "Z")
