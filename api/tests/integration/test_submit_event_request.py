"""SCRUM-46: an organiser submits a completed event request for coordinator review.

One test per acceptance criterion, plus the refusals (wrong owner, wrong role, no token,
unknown id, already submitted) that the Definition of Ready asks for.
"""

import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.orm import Session

from core.database import SessionLocal
from core.security import hash_password
from domain.event_request import field_names
from domain.event_status import EventStatus, InvalidTransitionError
from models.event_request import EventRequest
from models.user import User
from services import event_requests as service

MakeUser = Callable[..., User]
MakeClient = Callable[[User | None], httpx.AsyncClient]


def make_draft(db: Session, organiser: User, **overrides: object) -> EventRequest:
    """A complete draft owned by `organiser`; pass field=None to make it incomplete."""
    start = datetime.now(UTC) + timedelta(days=30)
    values: dict[str, object] = {
        "name": "Orientation Day",
        "purpose": "Welcome new students",
        "description": "Half-day programme with talks and a campus tour.",
        "start_at": start,
        "end_at": start + timedelta(hours=4),
        "expected_attendance": 200,
        "venue_requirement": "Auditorium, at least 200 seats",
        "accessibility_requirement": "Step-free access and hearing loop",
        "equipment_requirement": "Projector, two microphones",
        "layout_requirement": "Theatre style",
        "registration_requirement": "Open registration, capped at 200",
    }
    values.update(overrides)
    draft = EventRequest(organiser_id=organiser.id, status=EventStatus.DRAFT, **values)
    db.add(draft)
    db.flush()
    return draft


def content_of(request: EventRequest) -> dict[str, object]:
    return {name: getattr(request, name) for name in field_names()}


# --------------------------------------------------------------------------- AC1


@pytest.mark.story("SCRUM-46")
async def test_a_complete_draft_is_submitted_and_confirmed(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    draft = make_draft(db, organiser)

    async with make_client(organiser) as client:
        response = await client.post(f"/api/event-requests/{draft.id}/submit")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(draft.id)
    assert body["status"] == "submitted"

    db.refresh(draft)
    assert draft.status is EventStatus.SUBMITTED
    # submitted_at is the moment of submission, timezone-aware, and what the API returned.
    assert draft.submitted_at is not None
    assert draft.submitted_at.tzinfo is not None
    assert abs(datetime.now(UTC) - draft.submitted_at) < timedelta(seconds=30)
    assert body["submitted_at"] == draft.submitted_at.isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------- AC2


@pytest.mark.story("SCRUM-46")
async def test_an_incomplete_draft_is_refused_and_the_fields_are_named(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    draft = make_draft(db, organiser, name=None, expected_attendance=None)

    async with make_client(organiser) as client:
        response = await client.post(f"/api/event-requests/{draft.id}/submit")

    assert response.status_code == 422
    assert response.json()["detail"] == [
        {"field": "name", "reason": "is required"},
        {"field": "expected_attendance", "reason": "is required"},
    ]

    db.refresh(draft)
    assert draft.status is EventStatus.DRAFT
    assert draft.submitted_at is None


@pytest.mark.story("SCRUM-46")
async def test_an_invalid_draft_is_refused_with_the_reason(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    start = datetime.now(UTC) + timedelta(days=30)
    draft = make_draft(db, organiser, start_at=start, end_at=start - timedelta(hours=1))

    async with make_client(organiser) as client:
        response = await client.post(f"/api/event-requests/{draft.id}/submit")

    assert response.status_code == 422
    assert response.json()["detail"] == [{"field": "end_at", "reason": "must be after the start"}]


# --------------------------------------------------------------------------- AC3


@pytest.mark.story("SCRUM-46")
async def test_a_draft_can_still_be_edited(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    draft = make_draft(db, organiser)

    async with make_client(organiser) as client:
        response = await client.patch(
            f"/api/event-requests/{draft.id}", json={"name": "Orientation Week"}
        )

    assert response.status_code == 200
    assert response.json()["name"] == "Orientation Week"


@pytest.mark.story("SCRUM-46")
async def test_a_draft_field_can_be_cleared_with_null(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # A draft may be incomplete, so an explicit null is a real edit, not an omission:
    # exclude_unset keeps it, exclude_none would have dropped it.
    organiser = make_user("organiser")
    draft = make_draft(db, organiser)

    async with make_client(organiser) as client:
        response = await client.patch(f"/api/event-requests/{draft.id}", json={"description": None})

    assert response.status_code == 200
    assert response.json()["description"] is None
    db.refresh(draft)
    assert draft.description is None


@pytest.mark.story("SCRUM-46")
async def test_an_unknown_field_is_rejected_not_ignored(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # A typo in a field name must not look like a successful save.
    organiser = make_user("organiser")
    draft = make_draft(db, organiser)

    async with make_client(organiser) as client:
        response = await client.patch(
            f"/api/event-requests/{draft.id}", json={"descripton": "typo"}
        )

    assert response.status_code == 422
    db.refresh(draft)
    assert draft.description == "Half-day programme with talks and a campus tour."


@pytest.mark.story("SCRUM-46")
async def test_a_submitted_request_cannot_be_edited(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    draft = make_draft(db, organiser)

    async with make_client(organiser) as client:
        await client.post(f"/api/event-requests/{draft.id}/submit")
        response = await client.patch(
            f"/api/event-requests/{draft.id}", json={"name": "Changed after submission"}
        )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "This request has been submitted and can no longer be edited directly"
    )
    db.refresh(draft)
    assert draft.name == "Orientation Day"
    assert draft.status is EventStatus.SUBMITTED


@pytest.mark.story("SCRUM-46")
async def test_editing_with_a_naive_datetime_is_rejected(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # AGENTS.md §3: a datetime without a timezone never reaches the database, on any path.
    organiser = make_user("organiser")
    draft = make_draft(db, organiser)
    original_start = draft.start_at

    async with make_client(organiser) as client:
        response = await client.patch(
            f"/api/event-requests/{draft.id}", json={"start_at": "2026-12-01T09:00:00"}
        )

    assert response.status_code == 422
    db.refresh(draft)
    assert draft.start_at == original_start


@pytest.mark.story("SCRUM-46")
async def test_editing_with_another_timezone_is_stored_as_utc(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # AGENTS.md §3 says UTC at every layer, not merely "aware": 10:00 in +01:00 is stored
    # and returned as 09:00 UTC. The instant is the same; only the representation moves.
    organiser = make_user("organiser")
    draft = make_draft(db, organiser)

    async with make_client(organiser) as client:
        response = await client.patch(
            f"/api/event-requests/{draft.id}", json={"end_at": "2026-12-01T10:00:00+01:00"}
        )

    assert response.status_code == 200
    assert response.json()["end_at"] == "2026-12-01T09:00:00Z"
    db.refresh(draft)
    assert draft.end_at == datetime(2026, 12, 1, 9, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- AC4


@pytest.mark.story("SCRUM-46")
async def test_submission_changes_nothing_but_status_and_timestamp(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # AC4: no venue booking, equipment reservation or registration results from
    # submitting. Those tables do not exist yet, so the observable form of the rule is
    # that submission touches exactly the status and its timestamp - nothing else.
    organiser = make_user("organiser")
    draft = make_draft(db, organiser)
    before = content_of(draft)

    async with make_client(organiser) as client:
        response = await client.post(f"/api/event-requests/{draft.id}/submit")

    assert response.status_code == 200
    db.refresh(draft)
    assert content_of(draft) == before


# --------------------------------------------------------------------------- refusals


@pytest.mark.story("SCRUM-46")
async def test_another_organiser_cannot_submit_it(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    owner = make_user("organiser")
    someone_else = make_user("organiser")
    draft = make_draft(db, owner)

    async with make_client(someone_else) as client:
        response = await client.post(f"/api/event-requests/{draft.id}/submit")

    assert response.status_code == 403
    db.refresh(draft)
    assert draft.status is EventStatus.DRAFT


@pytest.mark.story("SCRUM-46")
async def test_a_coordinator_cannot_submit_it(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    owner = make_user("organiser")
    coordinator = make_user("coordinator")
    draft = make_draft(db, owner)

    async with make_client(coordinator) as client:
        response = await client.post(f"/api/event-requests/{draft.id}/submit")

    assert response.status_code == 403


@pytest.mark.story("SCRUM-46")
async def test_an_unauthenticated_call_is_rejected(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    draft = make_draft(db, make_user("organiser"))

    async with make_client(None) as client:
        response = await client.post(f"/api/event-requests/{draft.id}/submit")

    assert response.status_code == 401


@pytest.mark.story("SCRUM-46")
async def test_an_unknown_request_is_not_found(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("organiser")) as client:
        response = await client.post(f"/api/event-requests/{uuid.uuid4()}/submit")

    assert response.status_code == 404


@pytest.mark.story("SCRUM-46")
async def test_submitting_twice_is_a_conflict(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    draft = make_draft(db, organiser)

    async with make_client(organiser) as client:
        first = await client.post(f"/api/event-requests/{draft.id}/submit")
        second = await client.post(f"/api/event-requests/{draft.id}/submit")

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"] == "This request has already been submitted"


# --------------------------------------------------------------------------- listing


@pytest.mark.story("SCRUM-46")
async def test_an_organiser_lists_only_their_own_requests(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    mine = make_user("organiser")
    theirs = make_user("organiser")
    own = make_draft(db, mine)
    make_draft(db, theirs)

    async with make_client(mine) as client:
        response = await client.get("/api/event-requests")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [str(own.id)]


@pytest.mark.story("SCRUM-46")
async def test_requests_are_listed_newest_first(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    now = datetime.now(UTC)
    older = make_draft(db, organiser, name="Older", created_at=now - timedelta(days=2))
    newer = make_draft(db, organiser, name="Newer", created_at=now - timedelta(days=1))

    async with make_client(organiser) as client:
        response = await client.get("/api/event-requests")

    assert [row["id"] for row in response.json()] == [str(newer.id), str(older.id)]


@pytest.mark.story("SCRUM-46")
async def test_listing_requires_a_signed_in_organiser(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(None) as anonymous:
        assert (await anonymous.get("/api/event-requests")).status_code == 401

    async with make_client(make_user("coordinator")) as coordinator:
        assert (await coordinator.get("/api/event-requests")).status_code == 403


# --------------------------------------------------------------------------- concurrency


def _committed_draft() -> tuple[uuid.UUID, uuid.UUID]:
    """A real, committed organiser and complete draft — visible to every connection."""
    session = SessionLocal()
    try:
        organiser = User(
            email=f"{uuid.uuid4()}@example.com",
            password_hash=hash_password("password123"),
            roles=["organiser"],
        )
        session.add(organiser)
        session.flush()
        draft = make_draft(session, organiser)
        session.commit()
        return draft.id, organiser.id
    finally:
        session.close()


def _delete_committed(draft_id: uuid.UUID, organiser_id: uuid.UUID) -> None:
    session = SessionLocal()
    try:
        draft = session.get(EventRequest, draft_id)
        if draft is not None:
            session.delete(draft)
        organiser = session.get(User, organiser_id)
        if organiser is not None:
            session.delete(organiser)
        session.commit()
    finally:
        session.close()


@pytest.mark.story("SCRUM-46")
@pytest.mark.parametrize("attempt", range(5))
def test_simultaneous_submissions_yield_exactly_one_success(attempt: int) -> None:
    """Two organiser browsers double-click Submit at the same instant. The row lock in
    repositories.event_requests.get_for_update serialises them: one submits, the other
    then reads SUBMITTED and is refused. This needs two real transactions racing, which
    the rolled-back `db` fixture cannot express — so it commits and cleans up itself."""
    del attempt  # the run number only exists to repeat the race
    draft_id, organiser_id = _committed_draft()
    start_together = threading.Barrier(2)
    outcomes: list[str] = []

    def submit_once() -> None:
        session = SessionLocal()
        try:
            start_together.wait()
            service.submit(session, draft_id, organiser_id, datetime.now(UTC))
            outcomes.append("submitted")
        except InvalidTransitionError:
            outcomes.append("refused")
        finally:
            session.close()

    try:
        threads = [threading.Thread(target=submit_once) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert sorted(outcomes) == ["refused", "submitted"]
    finally:
        _delete_committed(draft_id, organiser_id)
