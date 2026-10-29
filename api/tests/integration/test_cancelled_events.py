"""SCRUM-88 AC6: the cancelled-event lists a Coordinator and a Lead open the history from.

Each list returns only events whose history the viewer may already read
(READ_EVENT_HISTORY, ADR-0062): the current assignee's own, or every one for a Lead.
Events are built in their status directly, because what is under test is which rows a
list returns, not how an event got cancelled (SCRUM-115 has its own tests).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from models.event_request import EventRequest
from models.user import User
from tests.integration.test_submit_event_request import MakeClient, MakeUser, make_draft

_ASSIGNED = "/api/event-requests/assigned-cancelled"
_ALL = "/api/event-requests/cancelled"
_T0 = datetime(2030, 3, 2, 1, 0, tzinfo=UTC)


def _event(db: Session, owner: User, status: EventStatus, **fields: object) -> EventRequest:
    event = make_draft(db, owner)
    event.status = status
    for field, value in fields.items():
        setattr(event, field, value)
    db.flush()
    return event


def _cancelled(
    db: Session, owner: User, coordinator: User | None, hours: int, name: str
) -> EventRequest:
    return _event(
        db,
        owner,
        EventStatus.CANCELLED,
        name=name,
        coordinator_id=None if coordinator is None else coordinator.id,
        cancelled_by_id=owner.id if coordinator is None else coordinator.id,
        cancelled_at=_T0 + timedelta(hours=hours),
        cancellation_reason=f"{name} reason",
    )


def _others(db: Session, owner: User, coordinator: User) -> set[uuid.UUID]:
    """One event in every other status, all assigned to `coordinator`."""
    return {
        _event(db, owner, status, coordinator_id=coordinator.id).id
        for status in EventStatus
        if status is not EventStatus.CANCELLED
    }


async def _ids(make_client: MakeClient, viewer: User, path: str) -> list[str]:
    async with make_client(viewer) as client:
        response = await client.get(path)
    assert response.status_code == 200
    return [row["id"] for row in response.json()]


@pytest.mark.story("SCRUM-88")
async def test_a_coordinator_sees_only_their_own_cancelled_events_newest_first(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    owner, me, other = make_user("organiser"), make_user("coordinator"), make_user("coordinator")
    older = _cancelled(db, owner, me, 1, "Older")
    newer = _cancelled(db, owner, me, 2, "Newer")
    theirs = _cancelled(db, owner, other, 3, "Theirs")
    never_assigned = _cancelled(db, owner, None, 4, "Never assigned")
    _others(db, owner, me)

    assert await _ids(make_client, me, _ASSIGNED) == [str(newer.id), str(older.id)]
    assert str(theirs.id) not in await _ids(make_client, me, _ASSIGNED)
    assert str(never_assigned.id) not in await _ids(make_client, me, _ASSIGNED)


@pytest.mark.story("SCRUM-88")
async def test_a_lead_sees_every_cancelled_event_and_nothing_else(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    owner, coordinator = make_user("organiser"), make_user("coordinator")
    assigned = _cancelled(db, owner, coordinator, 1, "Assigned")
    never_assigned = _cancelled(db, owner, None, 2, "Never assigned")
    others = _others(db, owner, coordinator)

    ids = await _ids(make_client, make_user("coordinator_lead"), _ALL)

    assert ids.index(str(never_assigned.id)) < ids.index(str(assigned.id))
    assert not {str(i) for i in others} & set(ids)


@pytest.mark.story("SCRUM-88")
async def test_a_row_carries_only_the_name_start_and_cancellation(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    owner, me = make_user("organiser"), make_user("coordinator")
    event = _cancelled(db, owner, me, 5, "Open day")

    async with make_client(me) as client:
        [row] = (await client.get(_ASSIGNED)).json()

    assert set(row) == {"id", "name", "start_at", "cancelled_at", "cancellation_reason"}
    assert (row["id"], row["name"], row["cancellation_reason"]) == (
        str(event.id),
        "Open day",
        "Open day reason",
    )
    assert datetime.fromisoformat(row["cancelled_at"]) == _T0 + timedelta(hours=5)
    assert event.start_at is not None
    assert datetime.fromisoformat(row["start_at"]) == event.start_at


@pytest.mark.story("SCRUM-88")
async def test_every_listed_event_opens_its_history_for_that_viewer(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """The lists show no event the viewer could not already read the history of."""
    owner, coordinator = make_user("organiser"), make_user("coordinator")
    _cancelled(db, owner, coordinator, 1, "Assigned")
    _cancelled(db, owner, None, 2, "Never assigned")

    for viewer, path in ((coordinator, _ASSIGNED), (make_user("coordinator_lead"), _ALL)):
        listed = await _ids(make_client, viewer, path)
        assert listed
        async with make_client(viewer) as client:
            for event_id in listed:
                response = await client.get(f"/api/event-requests/{event_id}/history")
                assert response.status_code == 200


@pytest.mark.story("SCRUM-88")
@pytest.mark.parametrize(
    ("path", "role", "expected"),
    [
        *[
            (path, role, 403)
            for path in (_ASSIGNED, _ALL)
            for role in ("organiser", "venue_staff", "tech_support", "attendee", "safety_officer")
        ],
        (_ALL, "coordinator", 403),
        (_ASSIGNED, "coordinator_lead", 403),
        (_ASSIGNED, None, 401),
        (_ALL, None, 401),
    ],
)
async def test_anyone_else_is_refused(
    path: str,
    role: str | None,
    expected: int,
    db: Session,
    make_user: MakeUser,
    make_client: MakeClient,
) -> None:
    caller = None if role is None else make_user(role)

    async with make_client(caller) as client:
        response = await client.get(path)

    assert response.status_code == expected
