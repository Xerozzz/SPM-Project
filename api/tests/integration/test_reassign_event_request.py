"""SCRUM-97: a Coordinator Lead reassigns an active request with immutable history.

TC-97-01 pins the migration (upgrade creates the history table, downgrade removes only
what the migration introduced). TC-97-02/03 prove owner replacement, permission
transfer and ordered history. TC-97-04 proves arrangements survive. TC-97-05/06 cover
the authorisation matrix and invalid replacements. TC-97-07 covers the concurrent
reassign conflict. TC-97-08 pins the chronological history view.
"""

import threading
import uuid
from datetime import UTC, datetime

import pytest
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from alembic import command
from core.database import SessionLocal, engine
from core.security import hash_password
from domain.event_status import EventStatus
from models.event_coordinator_assignment import EventCoordinatorAssignment
from models.event_request import EventRequest
from models.notification import Notification
from models.organisation import Organisation
from models.user import User
from repositories import coordinator_assignments as history_repo
from services import event_requests as service
from tests.integration.test_submit_event_request import MakeClient, MakeUser, make_draft


def _submitted(db: Session, organiser: User) -> EventRequest:
    """A Submitted request arranged directly, so tests control assignment exactly."""
    request = make_draft(db, organiser)
    request.status = EventStatus.SUBMITTED
    request.submitted_at = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
    db.flush()
    return request


def _assigned(db: Session, organiser: User, owner: User, lead: User) -> EventRequest:
    """A Submitted request owned by `owner`, with its first history entry recorded."""
    request = _submitted(db, organiser)
    return service.assign_coordinator(
        db, request.id, owner.id, datetime(2026, 4, 2, 9, 0, tzinfo=UTC), lead.id
    )


def _reassign_body(new_owner: User, current_owner: User) -> dict[str, str]:
    return {
        "coordinator_id": str(new_owner.id),
        "expected_current_coordinator_id": str(current_owner.id),
    }


# ------------------------------------------------------------------ TC-97-01


@pytest.mark.story("SCRUM-97")
def test_migration_creates_and_removes_only_the_history_table() -> None:
    """AC2 storage: upgrade creates the history table; downgrade removes only what
    migration 0016 introduced, leaving the requests table behind."""
    command.downgrade(Config("alembic.ini"), "0015")
    try:
        assert "event_coordinator_assignments" not in inspect(engine).get_table_names()
        command.upgrade(Config("alembic.ini"), "0016")
        assert "event_coordinator_assignments" in inspect(engine).get_table_names()
    finally:
        command.upgrade(Config("alembic.ini"), "head")
    assert "event_coordinator_assignments" in inspect(engine).get_table_names()
    assert "event_requests" in inspect(engine).get_table_names()


# ------------------------------------------------------------------ TC-97-02


@pytest.mark.story("SCRUM-97")
async def test_reassign_replaces_owner_and_appends_one_immutable_row(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1/AC2: B becomes the current owner, one history row records A→B with the
    acting Lead and a timezone-aware time, and the earlier entry never changes."""
    organiser = make_user("organiser")
    first = make_user("coordinator")
    second = make_user("coordinator")
    lead = make_user("coordinator_lead")
    request = _assigned(db, organiser, first, lead)
    before = history_repo.list_for_event(db, request.id)
    assert len(before) == 1
    assert before[0].previous_coordinator_id is None
    first_entry_id = before[0].id

    async with make_client(lead) as client:
        response = await client.post(
            f"/api/event-requests/{request.id}/reassign", json=_reassign_body(second, first)
        )

    assert response.status_code == 200
    assert response.json()["coordinator_id"] == str(second.id)
    db.refresh(request)
    assert request.coordinator_id == second.id
    assert request.assigned_at is not None
    assert request.assigned_at.tzinfo is not None
    rows = history_repo.list_for_event(db, request.id)
    assert len(rows) == 2
    assert rows[0].id == first_entry_id
    assert rows[0].previous_coordinator_id is None
    assert rows[0].new_coordinator_id == first.id
    assert rows[1].previous_coordinator_id == first.id
    assert rows[1].new_coordinator_id == second.id
    assert rows[1].acted_by_id == lead.id
    assert rows[1].assigned_at.tzinfo is not None


@pytest.mark.story("SCRUM-97")
async def test_owner_only_actions_transfer_to_the_new_owner(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1: after A→B the previous owner is refused owner-only actions and the new
    owner may clarify and decide while Submitted."""
    organiser = make_user("organiser")
    first = make_user("coordinator")
    second = make_user("coordinator")
    lead = make_user("coordinator_lead")
    request = _assigned(db, organiser, first, lead)

    async with make_client(lead) as client:
        reassign = await client.post(
            f"/api/event-requests/{request.id}/reassign", json=_reassign_body(second, first)
        )
    assert reassign.status_code == 200
    async with make_client(first) as client:
        refused = await client.post(
            f"/api/event-requests/{request.id}/clarifications",
            json={"message": "The previous owner tries to act."},
        )
    async with make_client(second) as client:
        clarification = await client.post(
            f"/api/event-requests/{request.id}/clarifications",
            json={"message": "Please confirm the headcount."},
        )
        approval = await client.post(f"/api/event-requests/{request.id}/approve")

    assert refused.status_code == 403
    assert clarification.status_code == 201
    assert approval.status_code == 200


# ------------------------------------------------------------------ TC-97-03


@pytest.mark.story("SCRUM-97")
@pytest.mark.story("SCRUM-105")
async def test_two_reassignments_produce_two_ordered_entries(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC2/AC7: A→B→C yields three chronological entries with correct previous/new
    owners and actors, viewable oldest first. SCRUM-105 (ADR-0047): each entry also
    names its people by email; the first assignment has no previous coordinator."""
    organiser = make_user("organiser")
    first = make_user("coordinator")
    second = make_user("coordinator")
    third = make_user("coordinator")
    lead = make_user("coordinator_lead")
    request = _assigned(db, organiser, first, lead)

    async with make_client(lead) as client:
        first_move = await client.post(
            f"/api/event-requests/{request.id}/reassign", json=_reassign_body(second, first)
        )
        second_move = await client.post(
            f"/api/event-requests/{request.id}/reassign", json=_reassign_body(third, second)
        )
        history = await client.get(f"/api/event-requests/{request.id}/assignment-history")

    assert first_move.status_code == 200
    assert second_move.status_code == 200
    assert history.status_code == 200
    entries = history.json()
    assert len(entries) == 3
    assert [entry["new_coordinator_id"] for entry in entries] == [
        str(first.id),
        str(second.id),
        str(third.id),
    ]
    assert [entry["previous_coordinator_id"] for entry in entries] == [
        None,
        str(first.id),
        str(second.id),
    ]
    assert all(entry["acted_by_id"] == str(lead.id) for entry in entries)
    assert [entry["new_coordinator_email"] for entry in entries] == [
        first.email,
        second.email,
        third.email,
    ]
    assert [entry["previous_coordinator_email"] for entry in entries] == [
        None,
        first.email,
        second.email,
    ]
    assert all(entry["acted_by_email"] == lead.email for entry in entries)
    assert all(
        set(entry)
        == {
            "id",
            "previous_coordinator_id",
            "previous_coordinator_email",
            "new_coordinator_id",
            "new_coordinator_email",
            "acted_by_id",
            "acted_by_email",
            "assigned_at",
        }
        for entry in entries
    )


# ------------------------------------------------------------------ TC-97-04


@pytest.mark.story("SCRUM-97")
async def test_reassignment_leaves_arrangements_unchanged(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC3: details, clarifications and venue bookings are value-for-value identical
    after the owner changes."""
    organiser = make_user("organiser")
    first = make_user("coordinator")
    second = make_user("coordinator")
    lead = make_user("coordinator_lead")
    request = _assigned(db, organiser, first, lead)
    async with make_client(first) as client:
        clarification = await client.post(
            f"/api/event-requests/{request.id}/clarifications",
            json={"message": "Please confirm the headcount."},
        )
    assert clarification.status_code == 201
    snapshot = {
        "name": request.name,
        "purpose": request.purpose,
        "description": request.description,
        "start_at": request.start_at,
        "end_at": request.end_at,
        "expected_attendance": request.expected_attendance,
        "venue_requirement": request.venue_requirement,
        "status": request.status,
        "organiser_id": request.organiser_id,
        "submitted_at": request.submitted_at,
    }
    clarification_count = db.execute(
        text("SELECT count(*) FROM event_clarifications WHERE event_request_id = :id"),
        {"id": str(request.id)},
    ).scalar()
    booking_count = db.execute(
        text("SELECT count(*) FROM venue_bookings WHERE event_request_id = :id"),
        {"id": str(request.id)},
    ).scalar()

    async with make_client(lead) as client:
        response = await client.post(
            f"/api/event-requests/{request.id}/reassign", json=_reassign_body(second, first)
        )

    assert response.status_code == 200
    db.refresh(request)
    for field, value in snapshot.items():
        assert getattr(request, field) == value
    assert (
        db.execute(
            text("SELECT count(*) FROM event_clarifications WHERE event_request_id = :id"),
            {"id": str(request.id)},
        ).scalar()
        == clarification_count
    )
    assert (
        db.execute(
            text("SELECT count(*) FROM venue_bookings WHERE event_request_id = :id"),
            {"id": str(request.id)},
        ).scalar()
        == booking_count
    )


# ------------------------------------------------------------------ TC-97-05


@pytest.mark.story("SCRUM-97")
@pytest.mark.story("SCRUM-105")
@pytest.mark.parametrize(
    ("caller_kind", "history_status"),
    [
        # SCRUM-105 (ADR-0047): the owning Organiser may now read the history, but
        # still may not reassign.
        ("owning_organiser", 200),
        ("unrelated_organiser", 403),
        ("coordinator", 403),
        ("venue_staff", 403),
        ("tech_support", 403),
        ("attendee", 403),
    ],
)
async def test_non_lead_roles_cannot_reassign_or_view_history(
    caller_kind: str,
    history_status: int,
    db: Session,
    make_user: MakeUser,
    make_client: MakeClient,
) -> None:
    """AC4: every non-Lead role gets 403 on reassign with no owner or history
    mutation. SCRUM-105: of these callers only the owning Organiser may read the
    history; an unrelated Organiser and an unassigned Coordinator still get 403."""
    organiser = make_user("organiser")
    first = make_user("coordinator")
    second = make_user("coordinator")
    lead = make_user("coordinator_lead")
    request = _assigned(db, organiser, first, lead)
    if caller_kind == "owning_organiser":
        caller = organiser
    elif caller_kind == "unrelated_organiser":
        caller = make_user("organiser")
    else:
        caller = make_user(caller_kind)

    async with make_client(caller) as client:
        reassign = await client.post(
            f"/api/event-requests/{request.id}/reassign", json=_reassign_body(second, first)
        )
        history = await client.get(f"/api/event-requests/{request.id}/assignment-history")

    assert reassign.status_code == 403
    assert history.status_code == history_status
    if history_status == 403:
        assert history.json() == {"detail": "Forbidden"}
    db.refresh(request)
    assert request.coordinator_id == first.id
    assert history_repo.count_for_event(db, request.id) == 1


@pytest.mark.story("SCRUM-97")
async def test_unauthenticated_caller_cannot_reassign_or_view_history(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC4 boundary: no token means 401, and nothing changes."""
    organiser = make_user("organiser")
    first = make_user("coordinator")
    second = make_user("coordinator")
    lead = make_user("coordinator_lead")
    request = _assigned(db, organiser, first, lead)

    async with make_client(None) as client:
        reassign = await client.post(
            f"/api/event-requests/{request.id}/reassign", json=_reassign_body(second, first)
        )
        history = await client.get(f"/api/event-requests/{request.id}/assignment-history")

    assert reassign.status_code == 401
    assert history.status_code == 401
    db.refresh(request)
    assert request.coordinator_id == first.id
    assert history_repo.count_for_event(db, request.id) == 1


# ------------------------------------------------------------------ TC-97-06


@pytest.mark.story("SCRUM-97")
@pytest.mark.parametrize("case", ["inactive", "non_coordinator", "missing", "same_owner"])
async def test_invalid_replacements_are_refused_without_history(
    case: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC5: an inactive user, an active non-coordinator, a missing user, or the
    current owner is a 422 with the owner kept and zero added history rows."""
    organiser = make_user("organiser")
    first = make_user("coordinator")
    lead = make_user("coordinator_lead")
    request = _assigned(db, organiser, first, lead)
    if case == "inactive":
        candidate_id = make_user("coordinator", is_active=False).id
    elif case == "non_coordinator":
        candidate_id = make_user("organiser").id
    elif case == "missing":
        candidate_id = uuid.uuid4()
    else:
        candidate_id = first.id

    async with make_client(lead) as client:
        response = await client.post(
            f"/api/event-requests/{request.id}/reassign",
            json={
                "coordinator_id": str(candidate_id),
                "expected_current_coordinator_id": str(first.id),
            },
        )

    assert response.status_code == 422
    db.refresh(request)
    assert request.coordinator_id == first.id
    assert history_repo.count_for_event(db, request.id) == 1


@pytest.mark.story("SCRUM-97")
async def test_reassigning_an_inactive_request_is_a_conflict(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC5 boundary: a request outside the active statuses cannot be reassigned —
    409 with the owner kept and zero added history rows."""
    organiser = make_user("organiser")
    first = make_user("coordinator")
    second = make_user("coordinator")
    lead = make_user("coordinator_lead")
    request = _assigned(db, organiser, first, lead)
    request.status = EventStatus.REJECTED
    db.flush()

    async with make_client(lead) as client:
        response = await client.post(
            f"/api/event-requests/{request.id}/reassign", json=_reassign_body(second, first)
        )

    assert response.status_code == 409
    db.refresh(request)
    assert request.coordinator_id == first.id
    assert history_repo.count_for_event(db, request.id) == 1


# ------------------------------------------------------------------ TC-97-07


def _delete_committed(request_id: uuid.UUID, *user_ids: uuid.UUID) -> None:
    """Remove a committed request, its history rows, and every user this helper
    created — the same cleanup pattern as the TC-98 concurrency test."""
    session = SessionLocal()
    try:
        # SCRUM-102: reassignment stages inbox rows referencing the request, so
        # they go before the history rows and the request itself.
        session.query(Notification).filter(Notification.event_request_id == request_id).delete()
        session.commit()
        session.query(EventCoordinatorAssignment).filter(
            EventCoordinatorAssignment.event_request_id == request_id
        ).delete()
        session.commit()
        request = session.get(EventRequest, request_id)
        organisation_id: uuid.UUID | None = None
        if request is not None:
            organiser = session.get(User, request.organiser_id)
            organisation_id = organiser.organisation_id if organiser is not None else None
            session.delete(request)
            session.commit()
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


CommittedAssigned = tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]


def _committed_assigned() -> CommittedAssigned:
    """A real, committed assigned request plus organiser, owner, two replacements and
    the acting Lead — visible to every connection, so two sessions can race."""
    session = SessionLocal()
    try:
        organisation = Organisation(name=f"Committed test organisation {uuid.uuid4()}")
        session.add(organisation)
        session.flush()

        def _user(*roles: str) -> User:
            user = User(
                email=f"{uuid.uuid4()}@example.com",
                password_hash=hash_password("password123"),
                roles=list(roles),
                organisation_id=organisation.id,
            )
            session.add(user)
            session.flush()
            return user

        organiser = _user("organiser")
        owner = _user("coordinator")
        second = _user("coordinator")
        third = _user("coordinator")
        lead = _user("coordinator_lead")
        request = make_draft(session, organiser)
        request.status = EventStatus.SUBMITTED
        request.submitted_at = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
        session.flush()
        service.assign_coordinator(
            session, request.id, owner.id, datetime(2026, 4, 2, 9, 0, tzinfo=UTC), lead.id
        )
        session.commit()
        return request.id, organiser.id, owner.id, second.id, third.id, lead.id
    finally:
        session.close()


@pytest.mark.story("SCRUM-97")
def test_concurrent_reassignments_yield_exactly_one_winner() -> None:
    """AC6: two Leads reassigning from owner A to different replacements at the same
    instant — one succeeds, one gets a stale conflict, and history agrees with the
    current owner."""
    request_id, organiser_id, owner_id, second_id, third_id, lead_id = _committed_assigned()
    start_together = threading.Barrier(2)
    outcomes: list[str] = []

    def reassign_once(new_owner_id: uuid.UUID) -> None:
        session = SessionLocal()
        try:
            start_together.wait()
            service.reassign_coordinator(
                session, request_id, new_owner_id, owner_id, lead_id, datetime.now(UTC)
            )
            outcomes.append(str(new_owner_id))
        except service.StaleAssignmentError:
            outcomes.append("conflict")
        finally:
            session.close()

    try:
        threads = [
            threading.Thread(target=reassign_once, args=(second_id,)),
            threading.Thread(target=reassign_once, args=(third_id,)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert sorted(outcomes) == sorted([str(second_id), "conflict"]) or sorted(
            outcomes
        ) == sorted([str(third_id), "conflict"])
        session = SessionLocal()
        try:
            winner = session.get(EventRequest, request_id)
            assert winner is not None
            assert str(winner.coordinator_id) in outcomes
            rows = history_repo.list_for_event(session, request_id)
            assert len(rows) == 2
            assert rows[-1].new_coordinator_id == winner.coordinator_id
            assert rows[-1].previous_coordinator_id == owner_id
        finally:
            session.close()
    finally:
        _delete_committed(request_id, organiser_id, owner_id, second_id, third_id, lead_id)


@pytest.mark.story("SCRUM-97")
async def test_stale_expected_owner_is_a_conflict(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC6 sequential: reassigning with a superseded expected owner is a 409 with the
    current owner kept and zero added history rows."""
    organiser = make_user("organiser")
    first = make_user("coordinator")
    second = make_user("coordinator")
    third = make_user("coordinator")
    lead = make_user("coordinator_lead")
    request = _assigned(db, organiser, first, lead)

    async with make_client(lead) as client:
        ok = await client.post(
            f"/api/event-requests/{request.id}/reassign", json=_reassign_body(second, first)
        )
        stale = await client.post(
            f"/api/event-requests/{request.id}/reassign", json=_reassign_body(third, first)
        )

    assert ok.status_code == 200
    assert stale.status_code == 409
    db.refresh(request)
    assert request.coordinator_id == second.id
    assert history_repo.count_for_event(db, request.id) == 2


# ------------------------------------------------------------------ TC-97-08


@pytest.mark.story("SCRUM-97")
async def test_history_view_covers_empty_single_and_many(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC7: a pre-migration assignment has no rows (empty list); one assignment has
    one entry; several entries with equal timestamps stay chronological via the
    stable id tiebreak."""
    organiser = make_user("organiser")
    first = make_user("coordinator")
    second = make_user("coordinator")
    lead = make_user("coordinator_lead")
    legacy = _submitted(db, organiser)
    legacy.coordinator_id = first.id
    legacy.assigned_at = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
    db.flush()
    request = _assigned(db, organiser, first, lead)

    async with make_client(lead) as client:
        empty = await client.get(f"/api/event-requests/{legacy.id}/assignment-history")
        single = await client.get(f"/api/event-requests/{request.id}/assignment-history")
        moved = await client.post(
            f"/api/event-requests/{request.id}/reassign", json=_reassign_body(second, first)
        )
        many = await client.get(f"/api/event-requests/{request.id}/assignment-history")

    assert empty.status_code == 200
    assert empty.json() == []
    assert single.status_code == 200
    assert len(single.json()) == 1
    assert moved.status_code == 200
    assert many.status_code == 200
    assert len(many.json()) == 2
    assert [entry["new_coordinator_id"] for entry in many.json()] == [
        str(first.id),
        str(second.id),
    ]


@pytest.mark.story("SCRUM-97")
def test_equal_timestamps_use_the_stable_id_tiebreak(db: Session, make_user: MakeUser) -> None:
    """AC7 boundary: entries sharing one timestamp still list oldest first."""
    organiser = make_user("organiser")
    first = make_user("coordinator")
    second = make_user("coordinator")
    lead = make_user("coordinator_lead")
    request = _assigned(db, organiser, first, lead)
    moment = datetime(2026, 4, 3, 9, 0, tzinfo=UTC)
    history_repo.append(db, request.id, first.id, second.id, lead.id, moment)
    history_repo.append(db, request.id, second.id, first.id, lead.id, moment)
    db.flush()

    rows = history_repo.list_for_event(db, request.id)

    assert len(rows) == 3
    assert rows[0].new_coordinator_id == first.id
    assert [row.assigned_at for row in rows] == sorted(row.assigned_at for row in rows)
    assert [row.id for row in rows[1:]] == sorted(row.id for row in rows[1:])
    assert {row.new_coordinator_id for row in rows[1:]} == {first.id, second.id}
