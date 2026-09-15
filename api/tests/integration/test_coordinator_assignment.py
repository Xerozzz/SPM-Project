"""SCRUM-34: on first submission, an event request is auto-assigned exactly one active
Event Coordinator by round-robin, skipping anyone already APPROVED that UTC date (the
ticket's "Confirmed"). Resubmission never retriggers assignment — in practice this can
only be observed as a 409, since the status machine (SCRUM-46) refuses a second submit
outright. Reassignment and accept/decline are separate, out-of-scope workflows.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from domain.coordinator_assignment import NoAvailableCoordinatorError
from domain.event_status import EventStatus, InvalidTransitionError
from models.event_request import EventRequest
from models.user import User
from services import event_requests as service
from tests.integration.test_submit_event_request import MakeClient, MakeUser, make_draft


def _approved(
    db: Session,
    organiser: User,
    coordinator: User,
    start_at: datetime,
    assigned_at: datetime | None = None,
) -> EventRequest:
    """An APPROVED event request, arranged directly for the test — the review/approval
    workflow (SCRUM-31) that would normally produce one is a separate, not-yet-built
    story. Built from `make_draft` so it satisfies the same content rules, then moved
    past the status machine by hand (test setup, not a code path any user can reach).

    `assigned_at` defaults to `start_at`'s day minus a small offset if not given, so a
    future `start_at` doesn't accidentally outrank real rotation history — pass it
    explicitly when a test cares about ordering.
    """
    request = make_draft(db, organiser, start_at=start_at, end_at=start_at + timedelta(hours=1))
    request.status = EventStatus.APPROVED
    request.coordinator_id = coordinator.id
    request.assigned_at = assigned_at if assigned_at is not None else start_at - timedelta(days=1)
    db.flush()
    return request

# ------------------------------------------------------------------ normal case


@pytest.mark.story("SCRUM-34")
def test_first_submission_assigns_the_next_coordinator_in_rotation(
    db: Session, make_user: MakeUser
) -> None:
    organiser = make_user("organiser")
    base = datetime(2026, 1, 1, tzinfo=UTC)
    coord_a = make_user("coordinator", created_at=base)
    coord_b = make_user("coordinator", created_at=base + timedelta(minutes=1))
    now = datetime(2026, 1, 2, tzinfo=UTC)
    first_draft = make_draft(db, organiser, start_at=datetime(2026, 3, 1, 9, 0, tzinfo=UTC))
    second_draft = make_draft(db, organiser, start_at=datetime(2026, 3, 2, 9, 0, tzinfo=UTC))

    first = service.submit(db, first_draft.id, organiser.id, now)
    second = service.submit(db, second_draft.id, organiser.id, now)

    assert first.coordinator_id == coord_a.id
    assert second.coordinator_id == coord_b.id
    assert first.status is EventStatus.SUBMITTED
    assert first.assigned_at is not None


@pytest.mark.story("SCRUM-34")
def test_inactive_coordinator_is_never_assigned(db: Session, make_user: MakeUser) -> None:
    organiser = make_user("organiser")
    base = datetime(2026, 1, 1, tzinfo=UTC)
    make_user("coordinator", is_active=False, created_at=base)
    active = make_user("coordinator", created_at=base + timedelta(minutes=1))
    now = datetime(2026, 1, 2, tzinfo=UTC)
    draft = make_draft(db, organiser, start_at=datetime(2026, 4, 1, 9, 0, tzinfo=UTC))

    result = service.submit(db, draft.id, organiser.id, now)

    assert result.coordinator_id == active.id


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
def test_submit_never_reassigns_a_request_that_already_has_a_coordinator(
    db: Session, make_user: MakeUser
) -> None:
    """The status machine (SCRUM-46) already blocks a second submit() outright, so this
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
def test_assignment_is_visible_to_the_organiser_and_to_any_coordinator(
    db: Session, make_user: MakeUser
) -> None:
    organiser = make_user("organiser")
    coord_a = make_user("coordinator")
    other_coordinator = make_user("coordinator")
    now = datetime(2026, 1, 2, tzinfo=UTC)
    draft = make_draft(db, organiser, start_at=datetime(2026, 8, 1, 9, 0, tzinfo=UTC))
    submitted = service.submit(db, draft.id, organiser.id, now)

    seen_by_owner = service.get(db, submitted.id, organiser.id, ["organiser"])
    seen_by_other_coordinator = service.get(db, submitted.id, other_coordinator.id, ["coordinator"])

    assert seen_by_owner.coordinator_id == coord_a.id
    assert seen_by_other_coordinator.coordinator_id == coord_a.id


# ---------------------------------------------------------------- boundary case


@pytest.mark.story("SCRUM-34")
def test_coordinator_approved_late_that_day_is_skipped_for_the_same_day(
    db: Session, make_user: MakeUser
) -> None:
    organiser = make_user("organiser")
    base = datetime(2026, 1, 1, tzinfo=UTC)
    busy = make_user("coordinator", created_at=base)
    free = make_user("coordinator", created_at=base + timedelta(minutes=1))
    _approved(db, organiser, busy, datetime(2026, 6, 10, 23, 59, tzinfo=UTC))
    now = datetime(2026, 1, 2, tzinfo=UTC)
    draft = make_draft(db, organiser, start_at=datetime(2026, 6, 10, 0, 0, 1, tzinfo=UTC))

    result = service.submit(db, draft.id, organiser.id, now)

    assert result.coordinator_id == free.id


@pytest.mark.story("SCRUM-34")
def test_approved_event_the_day_before_does_not_block_assignment(
    db: Session, make_user: MakeUser
) -> None:
    organiser = make_user("organiser")
    coord = make_user("coordinator")
    _approved(db, organiser, coord, datetime(2026, 6, 10, 23, 59, tzinfo=UTC))
    now = datetime(2026, 1, 2, tzinfo=UTC)
    draft = make_draft(db, organiser, start_at=datetime(2026, 6, 11, 0, 0, tzinfo=UTC))

    result = service.submit(db, draft.id, organiser.id, now)

    assert result.coordinator_id == coord.id


# ---------------------------------------------------------------------- conflict


@pytest.mark.story("SCRUM-34")
def test_conflict_when_every_active_coordinator_already_has_an_approved_event_that_day(
    db: Session, make_user: MakeUser
) -> None:
    organiser = make_user("organiser")
    coord = make_user("coordinator")
    _approved(db, organiser, coord, datetime(2026, 7, 1, 10, 0, tzinfo=UTC))
    now = datetime(2026, 1, 2, tzinfo=UTC)
    draft = make_draft(db, organiser, start_at=datetime(2026, 7, 1, 15, 0, tzinfo=UTC))

    with pytest.raises(NoAvailableCoordinatorError):
        service.submit(db, draft.id, organiser.id, now)


@pytest.mark.story("SCRUM-34")
async def test_submit_endpoint_returns_409_when_no_coordinator_is_available(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coord = make_user("coordinator")
    # Real wall-clock time: this goes through the HTTP endpoint, which stamps `now`
    # itself, so the date has to be safely in the future regardless of when this runs.
    clash_start = datetime(2027, 6, 1, 10, 0, tzinfo=UTC)
    _approved(db, organiser, coord, clash_start)
    draft = make_draft(
        db,
        organiser,
        start_at=clash_start + timedelta(hours=5),
        end_at=clash_start + timedelta(hours=6),
    )

    async with make_client(organiser) as client:
        response = await client.post(f"/api/event-requests/{draft.id}/submit")

    assert response.status_code == 409
    assert response.json()["detail"] == "No active coordinator is available for that date"


# ---------------------------------------------------------------- authorisation


@pytest.mark.story("SCRUM-34")
def test_get_is_forbidden_to_an_unrelated_organiser(db: Session, make_user: MakeUser) -> None:
    owner = make_user("organiser")
    other = make_user("organiser")
    make_user("coordinator")
    now = datetime(2026, 1, 2, tzinfo=UTC)
    draft = make_draft(db, owner, start_at=datetime(2026, 8, 2, 9, 0, tzinfo=UTC))
    submitted = service.submit(db, draft.id, owner.id, now)

    with pytest.raises(service.NotAuthorisedError):
        service.get(db, submitted.id, other.id, ["organiser"])


@pytest.mark.story("SCRUM-34")
async def test_read_endpoint_returns_404_for_an_unknown_request(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("organiser")) as client:
        response = await client.get(f"/api/event-requests/{uuid.uuid4()}")

    assert response.status_code == 404


@pytest.mark.story("SCRUM-34")
def test_get_raises_not_found_for_an_unknown_request(db: Session, make_user: MakeUser) -> None:
    organiser = make_user("organiser")

    with pytest.raises(service.EventRequestNotFoundError):
        service.get(db, uuid.uuid4(), organiser.id, ["organiser"])


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
    assert response.json()["coordinator_id"] == str(submitted.coordinator_id)


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
