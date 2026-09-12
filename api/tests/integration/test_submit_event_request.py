"""SCRUM-46: an organiser submits a completed event request for coordinator review.

One test per acceptance criterion, plus the refusals (wrong owner, wrong role, no token,
unknown id, already submitted) that the Definition of Ready asks for.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.orm import Session

from domain.event_request import field_names
from domain.event_status import EventStatus
from models.event_request import EventRequest
from models.user import User

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
    assert body["submitted_at"] is not None

    db.refresh(draft)
    assert draft.status is EventStatus.SUBMITTED
    assert draft.submitted_at is not None


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
    db.refresh(draft)
    assert draft.name == "Orientation Day"
    assert draft.status is EventStatus.SUBMITTED


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
