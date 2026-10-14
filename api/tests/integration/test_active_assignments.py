"""SCRUM-100: the Coordinator Lead active-assignment overview.

TC-100-02 proves mixed assigned/unassigned active rows return the required fields with
the correct current owners. TC-100-03 proves inactive statuses are excluded while
boundary active statuses stay. TC-100-04 covers zero/one/many rows with deterministic
ordering. TC-100-05 covers the Lead-only authorisation matrix.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from models.event_request import EventRequest
from models.user import User
from tests.integration.test_submit_event_request import MakeClient, MakeUser, make_draft

# Exactly the fields AC1 requires on each overview row — no more, no less.
# SCRUM-97 adds `coordinator_id` (the current owner's id, None when unassigned) so
# the Lead UI can send it back as `expected_current_coordinator_id` for optimistic
# concurrency (ADR-0021). It names the same owner as `coordinator_email`.
_OVERVIEW_FIELDS = {
    "id",
    "name",
    "status",
    "organiser_email",
    "start_at",
    "end_at",
    "coordinator_id",
    "coordinator_email",
}


def _active(
    db: Session,
    organiser: User,
    status: EventStatus,
    start_at: datetime,
    coordinator: User | None = None,
    **overrides: object,
) -> EventRequest:
    """An active request arranged directly, so tests control status and ownership."""
    request = make_draft(db, organiser, start_at=start_at, **overrides)
    request.status = status
    request.submitted_at = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
    if coordinator is not None:
        request.coordinator_id = coordinator.id
        request.assigned_at = datetime(2026, 4, 2, 9, 0, tzinfo=UTC)
    db.flush()
    return request


# ------------------------------------------------------------------ TC-100-02


@pytest.mark.story("SCRUM-100")
async def test_lead_sees_mixed_assigned_and_unassigned_active_rows(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1: assigned rows show their current coordinator, unassigned rows show null —
    both with exactly the required fields."""
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    lead = make_user("coordinator_lead")
    start = datetime(2026, 12, 1, 1, 0, tzinfo=UTC)
    owned = _active(db, organiser, EventStatus.SUBMITTED, start, coordinator, name="Owned request")
    open_row = _active(
        db,
        organiser,
        EventStatus.SUBMITTED,
        start + timedelta(hours=1),
        None,
        name="Open request",
    )

    async with make_client(lead) as client:
        response = await client.get("/api/event-requests/active-assignments")

    assert response.status_code == 200
    rows = {row["id"]: row for row in response.json()}
    assert set(rows) == {str(owned.id), str(open_row.id)}
    assert all(set(row) == _OVERVIEW_FIELDS for row in rows.values())
    assert rows[str(owned.id)]["coordinator_email"] == coordinator.email
    assert rows[str(owned.id)]["coordinator_id"] == str(coordinator.id)
    assert rows[str(owned.id)]["status"] == "submitted"
    assert rows[str(owned.id)]["name"] == "Owned request"
    assert rows[str(owned.id)]["organiser_email"] == organiser.email
    assert rows[str(open_row.id)]["coordinator_email"] is None
    assert rows[str(open_row.id)]["coordinator_id"] is None
    assert rows[str(open_row.id)]["name"] == "Open request"


# ------------------------------------------------------------------ TC-100-03


@pytest.mark.story("SCRUM-100")
async def test_inactive_statuses_are_excluded_while_boundary_active_stay(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC3: Draft and Rejected rows are absent; Submitted, Approved and Confirmed stay."""
    organiser = make_user("organiser")
    lead = make_user("coordinator_lead")
    start = datetime(2026, 12, 1, 1, 0, tzinfo=UTC)
    wanted = [
        _active(db, organiser, status, start + timedelta(hours=i), name=status.value)
        for i, status in enumerate(
            [EventStatus.SUBMITTED, EventStatus.APPROVED, EventStatus.CONFIRMED]
        )
    ]
    for i, status in enumerate([EventStatus.DRAFT, EventStatus.REJECTED]):
        _active(db, organiser, status, start + timedelta(hours=10 + i), name=status.value)

    async with make_client(lead) as client:
        response = await client.get("/api/event-requests/active-assignments")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [str(each.id) for each in wanted]


# ------------------------------------------------------------------ TC-100-04


@pytest.mark.story("SCRUM-100")
async def test_zero_one_and_many_rows_use_deterministic_order(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC5 + ordering: zero rows is an empty list; one returns one; many order by
    event start, with id as the stable secondary key for equal starts."""
    organiser = make_user("organiser")
    lead = make_user("coordinator_lead")

    async with make_client(lead) as client:
        empty = await client.get("/api/event-requests/active-assignments")
    assert empty.status_code == 200
    assert empty.json() == []

    start = datetime(2026, 12, 1, 1, 0, tzinfo=UTC)
    one = _active(db, organiser, EventStatus.SUBMITTED, start, name="Only")
    async with make_client(lead) as client:
        single = await client.get("/api/event-requests/active-assignments")
    assert single.status_code == 200
    assert [row["id"] for row in single.json()] == [str(one.id)]

    later = _active(db, organiser, EventStatus.APPROVED, start + timedelta(hours=2))
    earlier = _active(db, organiser, EventStatus.CONFIRMED, start - timedelta(hours=1))
    same_a = _active(db, organiser, EventStatus.SUBMITTED, start, name="Same A")
    same_b = _active(db, organiser, EventStatus.SUBMITTED, start, name="Same B")
    # `one`, `same_a`, and `same_b` share the same start, so the id tiebreak
    # decides their relative order — sort all three together.
    same_start_expected = sorted([one.id, same_a.id, same_b.id])
    async with make_client(lead) as client:
        many = await client.get("/api/event-requests/active-assignments")

    assert many.status_code == 200
    assert [row["id"] for row in many.json()] == [
        str(earlier.id),
        *[str(each) for each in same_start_expected],
        str(later.id),
    ]


# ------------------------------------------------------------------ TC-100-05


@pytest.mark.story("SCRUM-100")
@pytest.mark.parametrize("role", ["organiser", "coordinator", "venue_staff", "tech_support"])
async def test_non_lead_roles_cannot_access_the_overview(
    role: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC4: every non-Lead role is refused with 403 and receives no overview data."""
    organiser = make_user("organiser")
    _active(db, organiser, EventStatus.SUBMITTED, datetime(2026, 12, 1, 1, 0, tzinfo=UTC))
    caller = organiser if role == "organiser" else make_user(role)

    async with make_client(caller) as client:
        response = await client.get("/api/event-requests/active-assignments")

    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}


@pytest.mark.story("SCRUM-100")
async def test_unauthenticated_caller_cannot_access_the_overview(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC4 boundary: no token means 401, and still no overview data leaks."""
    _active(
        db,
        make_user("organiser"),
        EventStatus.SUBMITTED,
        datetime(2026, 12, 1, 1, 0, tzinfo=UTC),
    )

    async with make_client(None) as client:
        response = await client.get("/api/event-requests/active-assignments")

    assert response.status_code == 401
