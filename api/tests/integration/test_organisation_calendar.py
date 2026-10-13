"""SCRUM-87: organisation calendar visibility never grants ownership."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from models.event_request import EventRequest
from models.user import User

MakeUser = Callable[..., User]
MakeClient = Callable[[User | None], httpx.AsyncClient]
URL = "/api/event-requests/organisation-calendar"
START = datetime(2026, 11, 1, 9, tzinfo=UTC)


@pytest.mark.story("SCRUM-87")
@pytest.mark.parametrize("event_status", list(EventStatus))
async def test_own_and_colleague_events_are_separate_ordered_entries(
    db: Session, make_user: MakeUser, make_client: MakeClient, event_status: EventStatus
) -> None:
    owner = make_user("organiser")
    colleague = make_user("organiser", organisation_id=owner.organisation_id)
    outsider = make_user("organiser")
    rows = [
        EventRequest(
            organiser_id=user.id,
            name=name,
            start_at=START + timedelta(days=day),
            end_at=START + timedelta(days=day, hours=1),
            status=event_status,
        )
        for user, name, day in [(owner, "Own", 2), (colleague, "Shared", 0), (outsider, "Other", 1)]
    ]
    db.add_all(rows)
    db.flush()
    async with make_client(owner) as client:
        response = await client.get(URL)
        assert response.status_code == 200
        entries = response.json()
        assert [entry["id"] for entry in entries] == [str(rows[1].id), str(rows[0].id)]
        assert [entry["name"] for entry in entries] == ["Shared", "Own"]
        for entry in entries:
            assert set(entry) == {"id", "name", "start_at", "end_at", "status"}
            assert entry["status"] == event_status.value
            assert datetime.fromisoformat(entry["end_at"]) > datetime.fromisoformat(
                entry["start_at"]
            )
            assert (await client.get(f"/api/event-requests/{entry['id']}")).status_code == 200
        assert (await client.get(f"/api/event-requests/{rows[2].id}")).status_code == 403
        edit = await client.patch(f"/api/event-requests/{rows[1].id}", json={"name": "Changed"})
        assert edit.status_code == 403


@pytest.mark.story("SCRUM-87")
@pytest.mark.parametrize(
    "start,end",
    [
        (None, None),
        (START, None),
        (None, START),
        (START, START),
        (START, START - timedelta(hours=1)),
    ],
)
async def test_unusable_draft_dates_are_excluded(
    db: Session,
    make_user: MakeUser,
    make_client: MakeClient,
    start: datetime | None,
    end: datetime | None,
) -> None:
    owner = make_user("organiser")
    db.add(EventRequest(organiser_id=owner.id, start_at=start, end_at=end))
    db.flush()
    async with make_client(owner) as client:
        response = await client.get(URL)
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.story("SCRUM-87")
async def test_draft_owner_can_edit_but_colleague_cannot_edit_or_submit(
    make_user: MakeUser,
    make_client: MakeClient,
) -> None:
    owner = make_user("organiser")
    colleague = make_user("organiser", organisation_id=owner.organisation_id)
    async with make_client(owner) as client:
        created = await client.post(
            "/api/event-requests/drafts",
            json={
                "name": "Draft",
                "start_at": START.isoformat(),
                "end_at": (START + timedelta(hours=1)).isoformat(),
            },
        )
        assert created.status_code == 201
        path = f"/api/event-requests/{created.json()['id']}"
        assert (await client.patch(path, json={"name": "Updated"})).status_code == 200
    async with make_client(colleague) as client:
        assert (await client.get(URL)).json()[0]["name"] == "Updated"
        assert (await client.patch(path, json={"name": "Forbidden"})).status_code == 403
        assert (await client.post(f"{path}/submit")).status_code == 403
        assert (await client.get(path)).json()["name"] == "Updated"


@pytest.mark.story("SCRUM-87")
async def test_same_organisation_calendar_entry_opens_with_read_only_details(
    db: Session,
    make_user: MakeUser,
    make_client: MakeClient,
) -> None:
    owner = make_user("organiser")
    colleague = make_user("organiser", organisation_id=owner.organisation_id)
    request = EventRequest(
        organiser_id=owner.id,
        name="Colleague conference",
        purpose="Shared planning",
        description="Details visible to the organisation.",
        start_at=START,
        end_at=START + timedelta(hours=2),
    )
    db.add(request)
    db.flush()

    async with make_client(colleague) as client:
        calendar = await client.get(URL)
        detail = await client.get(f"/api/event-requests/{request.id}")
        edit = await client.patch(
            f"/api/event-requests/{request.id}", json={"description": "Not allowed"}
        )

    assert [row["id"] for row in calendar.json()] == [str(request.id)]
    assert detail.status_code == 200
    assert detail.json()["name"] == "Colleague conference"
    assert detail.json()["purpose"] == "Shared planning"
    assert detail.json()["description"] == "Details visible to the organisation."
    assert edit.status_code == 403


@pytest.mark.story("SCRUM-87")
async def test_coordinator_event_access_is_unchanged(
    db: Session,
    make_user: MakeUser,
    make_client: MakeClient,
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    draft = EventRequest(
        organiser_id=organiser.id,
        name="Draft",
        start_at=START,
        end_at=START + timedelta(hours=1),
    )
    submitted = EventRequest(
        organiser_id=organiser.id,
        name="Submitted",
        status=EventStatus.SUBMITTED,
        start_at=START,
        end_at=START + timedelta(hours=1),
    )
    db.add_all([draft, submitted])
    db.flush()

    async with make_client(coordinator) as client:
        calendar = await client.get(URL)
        draft_detail = await client.get(f"/api/event-requests/{draft.id}")
        submitted_detail = await client.get(f"/api/event-requests/{submitted.id}")

    assert calendar.status_code == 403
    assert draft_detail.status_code == 403
    assert submitted_detail.status_code == 200


@pytest.mark.story("SCRUM-87")
@pytest.mark.parametrize("role", [None, "coordinator", "venue_staff", "tech_support", "attendee"])
async def test_calendar_requires_organiser(
    make_user: MakeUser,
    make_client: MakeClient,
    role: str | None,
) -> None:
    async with make_client(make_user(role) if role else None) as client:
        response = await client.get(URL)
    assert response.status_code == (403 if role else 401)
