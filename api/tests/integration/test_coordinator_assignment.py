"""SCRUM-34: on first submission, an event request is auto-assigned exactly one active
Event Coordinator by round-robin, skipping anyone already CONFIRMED for that Singapore
calendar date (the ticket's "Confirmed"). Resubmission never retriggers assignment — in
practice this can only be observed as a 409, since the status machine (SCRUM-46) refuses
a second submit outright. Reassignment and accept/decline are separate, out-of-scope
workflows.
"""

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from domain.event_status import EventStatus, InvalidTransitionError
from models.event_request import EventRequest
from models.user import User
from repositories.event_requests import coordinator_ids_confirmed_on
from services import event_requests as service
from tests.integration.test_submit_event_request import MakeClient, MakeUser, make_draft


def _confirmed(
    db: Session,
    organiser: User,
    coordinator: User,
    start_at: datetime,
    assigned_at: datetime | None = None,
) -> EventRequest:
    """A CONFIRMED event request, arranged directly for the test — the review/approval
    workflow (SCRUM-31) that would normally produce one is a separate, not-yet-built
    story. Built from `make_draft` so it satisfies the same content rules, then moved
    past the status machine by hand (test setup, not a code path any user can reach).

    `assigned_at` defaults to `start_at`'s day minus a small offset if not given, so a
    future `start_at` doesn't accidentally outrank real rotation history — pass it
    explicitly when a test cares about ordering.
    """
    request = make_draft(db, organiser, start_at=start_at, end_at=start_at + timedelta(hours=1))
    request.status = EventStatus.CONFIRMED
    request.coordinator_id = coordinator.id
    request.assigned_at = assigned_at if assigned_at is not None else start_at - timedelta(days=1)
    db.flush()
    return request


def _in_status(
    db: Session, organiser: User, coordinator: User, start_at: datetime, status: EventStatus
) -> EventRequest:
    """An event request in `status`, with a coordinator, arranged directly for the test.
    Exists to prove that only CONFIRMED counts as a round-robin conflict."""
    request = make_draft(db, organiser, start_at=start_at, end_at=start_at + timedelta(hours=1))
    request.status = status
    request.coordinator_id = coordinator.id
    request.assigned_at = start_at - timedelta(days=1)
    db.flush()
    return request


# Every status that must NOT block assignment. Derived from the enum rather than listed, so
# when SCRUM-31 adds APPROVED (clarification row 91: approved means Planning, not confirmed)
# it is covered here automatically.
_NOT_CONFIRMED = [status for status in EventStatus if status is not EventStatus.CONFIRMED]


# ------------------------------------------------------------------ normal case


@pytest.mark.story("SCRUM-34")
@pytest.mark.story("SCRUM-101")
def test_first_submission_assigns_the_next_coordinator_in_rotation(
    db: Session, make_user: MakeUser
) -> None:
    """SCRUM-101: submission leaves the request unassigned for Lead triage.

    Supersedes the SCRUM-34 round-robin expectation: no coordinator is assigned at
    submit time, even when active coordinators exist. See ADR-0020."""
    organiser = make_user("organiser")
    base = datetime(2026, 1, 1, tzinfo=UTC)
    make_user("coordinator", created_at=base)
    make_user("coordinator", created_at=base + timedelta(minutes=1))
    now = datetime(2026, 1, 2, tzinfo=UTC)
    first_draft = make_draft(db, organiser, start_at=datetime(2026, 3, 1, 9, 0, tzinfo=UTC))
    second_draft = make_draft(db, organiser, start_at=datetime(2026, 3, 2, 9, 0, tzinfo=UTC))

    first = service.submit(db, first_draft.id, organiser.id, now)
    second = service.submit(db, second_draft.id, organiser.id, now)

    assert first.coordinator_id is None
    assert second.coordinator_id is None
    assert first.status is EventStatus.SUBMITTED
    assert first.assigned_at is None


@pytest.mark.story("SCRUM-34")
@pytest.mark.story("SCRUM-101")
def test_inactive_coordinator_is_never_assigned(db: Session, make_user: MakeUser) -> None:
    """SCRUM-101: submission assigns nobody, so coordinator activity is irrelevant."""
    organiser = make_user("organiser")
    base = datetime(2026, 1, 1, tzinfo=UTC)
    make_user("coordinator", is_active=False, created_at=base)
    make_user("coordinator", created_at=base + timedelta(minutes=1))
    now = datetime(2026, 1, 2, tzinfo=UTC)
    draft = make_draft(db, organiser, start_at=datetime(2026, 4, 1, 9, 0, tzinfo=UTC))

    result = service.submit(db, draft.id, organiser.id, now)

    assert result.coordinator_id is None
    assert result.assigned_at is None


@pytest.mark.story("SCRUM-34")
def test_resubmission_does_not_change_the_existing_assignment(
    db: Session, make_user: MakeUser
) -> None:
    organiser = make_user("organiser")
    make_user("coordinator")
    make_user("coordinator")
    now = datetime(2026, 1, 2, tzinfo=UTC)
    draft = make_draft(db, organiser, start_at=datetime(2026, 5, 1, 9, 0, tzinfo=UTC))

    first = service.submit(db, draft.id, organiser.id, now)
    with pytest.raises(InvalidTransitionError):
        service.submit(db, draft.id, organiser.id, now)

    db.refresh(draft)
    assert draft.coordinator_id == first.coordinator_id
    assert draft.assigned_at == first.assigned_at


@pytest.mark.story("SCRUM-34")
@pytest.mark.story("SCRUM-101")
def test_submit_never_reassigns_a_request_that_already_has_a_coordinator(
    db: Session, make_user: MakeUser
) -> None:
    """SCRUM-101: submission leaves any pre-existing assignment untouched.

    The status machine (SCRUM-46) already blocks a second submit() outright, so this
    guard is currently unreachable through it — but it also protects a future
    resubmission path (e.g. after SCRUM-30's clarification round) that might call
    submit() again on a DRAFT that already carries an assignment."""
    organiser = make_user("organiser")
    coord_a = make_user("coordinator")
    make_user("coordinator")
    now = datetime(2026, 1, 2, tzinfo=UTC)
    draft = make_draft(db, organiser, start_at=datetime(2026, 5, 2, 9, 0, tzinfo=UTC))
    draft.coordinator_id = coord_a.id
    draft.assigned_at = now
    db.flush()

    result = service.submit(db, draft.id, organiser.id, now)

    assert result.coordinator_id == coord_a.id
    assert result.assigned_at == now


@pytest.mark.story("SCRUM-34")
@pytest.mark.story("SCRUM-101")
async def test_assignment_is_visible_to_the_organiser_and_to_any_coordinator(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """SCRUM-101: a fresh submission reads back unassigned to every viewer."""
    organiser = make_user("organiser")
    make_user("coordinator")
    other_coordinator = make_user("coordinator")
    now = datetime(2026, 1, 2, tzinfo=UTC)
    draft = make_draft(db, organiser, start_at=datetime(2026, 8, 1, 9, 0, tzinfo=UTC))
    submitted = service.submit(db, draft.id, organiser.id, now)

    async with make_client(organiser) as owner_client:
        seen_by_owner = await owner_client.get(f"/api/event-requests/{submitted.id}")
    async with make_client(other_coordinator) as coordinator_client:
        seen_by_other = await coordinator_client.get(f"/api/event-requests/{submitted.id}")

    assert seen_by_owner.status_code == 200
    assert seen_by_owner.json()["coordinator_id"] is None
    assert seen_by_other.status_code == 200
    assert seen_by_other.json()["coordinator_id"] is None


@pytest.mark.story("SCRUM-34")
@pytest.mark.story("SCRUM-101")
def test_confirmed_event_in_the_last_minute_of_the_day_still_blocks_that_day(
    db: Session, make_user: MakeUser
) -> None:
    """SCRUM-101: a same-day CONFIRMED event no longer blocks submission.

    The request waits unassigned in the Lead queue instead of failing with 409.
    The pure conflict rule itself is still covered by the unit tests for
    `select_next_coordinator` and by `coordinator_ids_confirmed_on` below."""
    organiser = make_user("organiser")
    busy = make_user("coordinator")
    _confirmed(db, organiser, busy, datetime(2026, 6, 10, 15, 59, tzinfo=UTC))
    now = datetime(2026, 1, 2, tzinfo=UTC)
    draft = make_draft(db, organiser, start_at=datetime(2026, 6, 9, 16, 0, 1, tzinfo=UTC))

    result = service.submit(db, draft.id, organiser.id, now)

    assert result.status is EventStatus.SUBMITTED
    assert result.coordinator_id is None


@pytest.mark.story("SCRUM-34")
@pytest.mark.story("SCRUM-101")
def test_confirmed_event_the_day_before_does_not_block_assignment(
    db: Session, make_user: MakeUser
) -> None:
    organiser = make_user("organiser")
    coord = make_user("coordinator")
    _confirmed(db, organiser, coord, datetime(2026, 6, 10, 12, 0, tzinfo=UTC))
    now = datetime(2026, 1, 2, tzinfo=UTC)
    draft = make_draft(db, organiser, start_at=datetime(2026, 6, 11, 4, 0, tzinfo=UTC))

    result = service.submit(db, draft.id, organiser.id, now)

    assert result.status is EventStatus.SUBMITTED
    assert result.coordinator_id is None


# ---------------------------------------------------------------------- conflict


@pytest.mark.story("SCRUM-34")
@pytest.mark.story("SCRUM-101")
def test_conflict_when_every_active_coordinator_already_has_a_confirmed_event_that_day(
    db: Session, make_user: MakeUser
) -> None:
    """SCRUM-101: a fully-booked day no longer refuses submission (see ADR-0020)."""
    organiser = make_user("organiser")
    coord = make_user("coordinator")
    _confirmed(db, organiser, coord, datetime(2026, 7, 1, 10, 0, tzinfo=UTC))
    now = datetime(2026, 1, 2, tzinfo=UTC)
    draft = make_draft(db, organiser, start_at=datetime(2026, 7, 1, 15, 0, tzinfo=UTC))

    result = service.submit(db, draft.id, organiser.id, now)

    assert result.status is EventStatus.SUBMITTED
    assert result.coordinator_id is None


@pytest.mark.story("SCRUM-34")
@pytest.mark.parametrize("status", _NOT_CONFIRMED, ids=[s.value for s in _NOT_CONFIRMED])
@pytest.mark.story("SCRUM-101")
def test_only_a_confirmed_event_blocks_assignment(
    db: Session, make_user: MakeUser, status: EventStatus
) -> None:
    """SCRUM-101: submission never assigns, whatever else exists that day.

    The CONFIRMED-only shape of the conflict rule itself is still covered by the
    pure `select_next_coordinator` unit tests and `coordinator_ids_confirmed_on`."""
    organiser = make_user("organiser")
    coord = make_user("coordinator")
    _in_status(db, organiser, coord, datetime(2026, 6, 10, 6, 0, tzinfo=UTC), status)
    now = datetime(2026, 1, 2, tzinfo=UTC)
    draft = make_draft(db, organiser, start_at=datetime(2026, 6, 10, 8, 0, tzinfo=UTC))

    result = service.submit(db, draft.id, organiser.id, now)

    assert result.status is EventStatus.SUBMITTED
    assert result.coordinator_id is None


@pytest.mark.story("SCRUM-34")
@pytest.mark.story("SCRUM-101")
async def test_submit_endpoint_returns_409_when_no_coordinator_is_available(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """SCRUM-101: even a fully-booked day submits cleanly into the Lead queue."""
    organiser = make_user("organiser")
    coord = make_user("coordinator")
    # Real wall-clock time: this goes through the HTTP endpoint, which stamps `now`
    # itself, so the date has to be safely in the future regardless of when this runs.
    # Anchored to SGT noon so +5h stays on the same Singapore calendar day.
    sgt_noon = (
        (datetime.now(UTC) + timedelta(days=365))
        .astimezone(ZoneInfo("Asia/Singapore"))
        .replace(hour=12, minute=0, second=0, microsecond=0)
    )
    clash_start = sgt_noon.astimezone(UTC)
    _confirmed(db, organiser, coord, clash_start)
    draft = make_draft(
        db,
        organiser,
        start_at=clash_start + timedelta(hours=5),
        end_at=clash_start + timedelta(hours=6),
    )

    async with make_client(organiser) as client:
        response = await client.post(f"/api/event-requests/{draft.id}/submit")

    assert response.status_code == 200
    assert response.json()["status"] == "submitted"
    assert response.json()["coordinator_id"] is None


# ---------------------------------------------------------------- authorisation


@pytest.mark.story("SCRUM-34")
async def test_read_endpoint_is_forbidden_to_an_organiser_from_another_organisation(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    owner = make_user("organiser")
    other = make_user("organiser")  # make_user gives each user its own organisation
    make_user("coordinator")
    now = datetime(2026, 1, 2, tzinfo=UTC)
    draft = make_draft(db, owner, start_at=datetime(2026, 8, 2, 9, 0, tzinfo=UTC))
    submitted = service.submit(db, draft.id, owner.id, now)

    async with make_client(other) as client:
        response = await client.get(f"/api/event-requests/{submitted.id}")

    assert response.status_code == 403


@pytest.mark.story("SCRUM-34")
async def test_read_endpoint_returns_404_for_an_unknown_request(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("organiser")) as client:
        response = await client.get(f"/api/event-requests/{uuid.uuid4()}")

    assert response.status_code == 404


@pytest.mark.story("SCRUM-34")
async def test_read_endpoint_returns_404_for_an_unknown_request_to_a_coordinator_too(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    # Not-found is decided before any role rule, so a coordinator sees the same 404.
    async with make_client(make_user("coordinator")) as client:
        response = await client.get(f"/api/event-requests/{uuid.uuid4()}")

    assert response.status_code == 404


@pytest.mark.story("SCRUM-34")
async def test_read_endpoint_requires_authentication(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    make_user("coordinator")
    now = datetime(2026, 1, 2, tzinfo=UTC)
    draft = make_draft(db, organiser, start_at=datetime(2026, 9, 10, 9, 0, tzinfo=UTC))
    submitted = service.submit(db, draft.id, organiser.id, now)

    async with make_client(None) as client:
        response = await client.get(f"/api/event-requests/{submitted.id}")

    assert response.status_code == 401


@pytest.mark.story("SCRUM-34")
async def test_read_endpoint_returns_the_request_to_its_organiser(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    make_user("coordinator")
    now = datetime(2026, 1, 2, tzinfo=UTC)
    draft = make_draft(db, organiser, start_at=datetime(2026, 9, 11, 9, 0, tzinfo=UTC))
    submitted = service.submit(db, draft.id, organiser.id, now)

    async with make_client(organiser) as client:
        response = await client.get(f"/api/event-requests/{submitted.id}")

    assert response.status_code == 200
    assert response.json()["coordinator_id"] is None


@pytest.mark.story("SCRUM-34")
async def test_coordinator_can_view_but_not_edit_an_unassigned_event(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    make_user("coordinator")
    unassigned = make_user("coordinator")
    now = datetime(2026, 1, 2, tzinfo=UTC)
    draft = make_draft(db, organiser, start_at=datetime(2026, 9, 12, 9, 0, tzinfo=UTC))
    submitted = service.submit(db, draft.id, organiser.id, now)

    async with make_client(unassigned) as client:
        view = await client.get(f"/api/event-requests/{submitted.id}")
        edit = await client.patch(f"/api/event-requests/{submitted.id}", json={"name": "Hijacked"})

    assert view.status_code == 200
    assert edit.status_code == 403


@pytest.mark.story("SCRUM-34")
def test_overnight_confirmed_event_blocks_the_later_day(db: Session, make_user: MakeUser) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    _confirmed(
        db,
        organiser,
        coordinator,
        # 23:30 SGT on 30 June to 00:30 SGT on 1 July: starts before 1 July's window opens
        # (30 June 16:00 UTC) and ends inside it. A start_at-only filter would miss this.
        start_at=datetime(2026, 6, 30, 15, 30, tzinfo=UTC),
        assigned_at=datetime(2026, 6, 1, tzinfo=UTC),
    )
    unavailable = coordinator_ids_confirmed_on(db, datetime(2026, 7, 1, 12, 0, tzinfo=UTC))
    assert coordinator.id in unavailable
