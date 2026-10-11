"""SCRUM-101: the Coordinator Lead unassigned queue.

TC-101-01 proves submission leaves the request unassigned even with zero active
coordinators (no round-robin failure). TC-101-02..06 cover the queue itself: empty,
one row with exactly the required fields, filtering across statuses and assignment,
oldest-first ordering with a stable secondary key, and the Lead-only authorisation
matrix.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from models.event_request import EventRequest
from models.user import User
from tests.integration.test_submit_event_request import MakeClient, MakeUser, make_draft

# Exactly the fields AC2 requires on each queue row — no more, no less.
_QUEUE_FIELDS = {
    "id",
    "name",
    "organiser_id",
    "start_at",
    "end_at",
    "expected_attendance",
    "submitted_at",
}


def _submitted(
    db: Session, organiser: User, submitted_at: datetime, **overrides: object
) -> EventRequest:
    """A Submitted request arranged directly, so tests control `submitted_at` exactly."""
    request = make_draft(db, organiser, **overrides)
    request.status = EventStatus.SUBMITTED
    request.submitted_at = submitted_at
    db.flush()
    return request


# ------------------------------------------------------------------ TC-101-01


@pytest.mark.story("SCRUM-101")
async def test_submit_leaves_request_unassigned_with_no_coordinators(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1: a complete draft submits cleanly with zero active coordinators in the
    database — the legacy round-robin 409 cannot fire because submit never assigns."""
    organiser = make_user("organiser")
    draft = make_draft(db, organiser)

    async with make_client(organiser) as client:
        response = await client.post(f"/api/event-requests/{draft.id}/submit")

    assert response.status_code == 200
    assert response.json()["status"] == "submitted"
    assert response.json()["coordinator_id"] is None
    db.refresh(draft)
    assert draft.status is EventStatus.SUBMITTED
    assert draft.coordinator_id is None
    assert draft.assigned_at is None


# ------------------------------------------------------------- TC-101-02/03


@pytest.mark.story("SCRUM-101")
async def test_lead_receives_empty_list_when_queue_is_empty(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC2 boundary: zero queue rows is a 200 with an empty list, not a 404."""
    lead = make_user("coordinator_lead")

    async with make_client(lead) as client:
        response = await client.get("/api/event-requests/unassigned")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.story("SCRUM-101")
async def test_lead_receives_exactly_the_required_fields(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC2: one unassigned Submitted request returns every required field and no
    unrelated private fields (status, decision, rejection reason, timestamps)."""
    organiser = make_user("organiser")
    lead = make_user("coordinator_lead")
    submitted_at = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
    request = _submitted(db, organiser, submitted_at)

    async with make_client(lead) as client:
        response = await client.get("/api/event-requests/unassigned")

    assert response.status_code == 200
    (row,) = response.json()
    assert set(row) == _QUEUE_FIELDS
    assert request.start_at is not None and request.end_at is not None
    assert row["id"] == str(request.id)
    assert row["name"] == "Orientation Day"
    assert row["organiser_id"] == str(organiser.id)
    assert row["expected_attendance"] == 200
    assert row["submitted_at"] == submitted_at.isoformat().replace("+00:00", "Z")
    assert row["start_at"] == request.start_at.isoformat().replace("+00:00", "Z")
    assert row["end_at"] == request.end_at.isoformat().replace("+00:00", "Z")


# ------------------------------------------------------------------ TC-101-04


@pytest.mark.story("SCRUM-101")
async def test_only_unassigned_submitted_requests_appear(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC3: assigned requests and anything outside Submitted are excluded."""
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    lead = make_user("coordinator_lead")
    at = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
    wanted = _submitted(db, organiser, at, name="Wanted")
    make_draft(db, organiser, name="Draft")  # never submitted
    assigned = _submitted(db, organiser, at, name="Assigned")
    assigned.coordinator_id = coordinator.id
    for status, name in [
        (EventStatus.APPROVED, "Approved"),
        (EventStatus.REJECTED, "Rejected"),
        (EventStatus.CONFIRMED, "Confirmed"),
    ]:
        row = _submitted(db, organiser, at, name=name)
        row.status = status
    db.flush()

    async with make_client(lead) as client:
        response = await client.get("/api/event-requests/unassigned")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [str(wanted.id)]


# ------------------------------------------------------------------ TC-101-05


@pytest.mark.story("SCRUM-101")
async def test_queue_is_ordered_oldest_submission_first(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC5: oldest `submitted_at` first across distinct timestamps."""
    organiser = make_user("organiser")
    lead = make_user("coordinator_lead")
    base = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
    middle = _submitted(db, organiser, base + timedelta(hours=1), name="Middle")
    oldest = _submitted(db, organiser, base, name="Oldest")
    newest = _submitted(db, organiser, base + timedelta(hours=2), name="Newest")

    async with make_client(lead) as client:
        response = await client.get("/api/event-requests/unassigned")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [
        str(oldest.id),
        str(middle.id),
        str(newest.id),
    ]


@pytest.mark.story("SCRUM-101")
async def test_equal_timestamps_fall_back_to_stable_id_order(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC5 boundary: two rows sharing a timestamp come back in id order, so the
    queue is deterministic even when submissions land in the same instant."""
    organiser = make_user("organiser")
    lead = make_user("coordinator_lead")
    at = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
    first = _submitted(db, organiser, at, name="First")
    second = _submitted(db, organiser, at, name="Second")
    expected = sorted([first.id, second.id])

    async with make_client(lead) as client:
        response = await client.get("/api/event-requests/unassigned")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [str(each) for each in expected]


# ------------------------------------------------------------------ TC-101-06


@pytest.mark.story("SCRUM-101")
@pytest.mark.parametrize("role", ["organiser", "coordinator", "venue_staff", "tech_support"])
async def test_non_lead_roles_cannot_access_the_queue(
    role: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC4: every non-Lead role is refused with 403 and receives no queue data."""
    organiser = make_user("organiser")
    _submitted(db, organiser, datetime(2026, 4, 1, 9, 0, tzinfo=UTC))
    caller = organiser if role == "organiser" else make_user(role)

    async with make_client(caller) as client:
        response = await client.get("/api/event-requests/unassigned")

    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}


@pytest.mark.story("SCRUM-101")
async def test_unauthenticated_caller_cannot_access_the_queue(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC4 boundary: no token means 401, and still no queue data leaks."""
    _submitted(db, make_user("organiser"), datetime(2026, 4, 1, 9, 0, tzinfo=UTC))

    async with make_client(None) as client:
        response = await client.get("/api/event-requests/unassigned")

    assert response.status_code == 401
