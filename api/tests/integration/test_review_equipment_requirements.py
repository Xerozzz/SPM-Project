"""SCRUM-44: Technical Support Staff review equipment requirements.

Against real PostgreSQL, reusing SCRUM-43's arrangement: an approved event with an
assigned coordinator and a catalogue holding Projector and Microphone. The review list is
across every event, so assertions look only at the events each test created.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.equipment_requirement import RequirementReview
from domain.event_status import EventStatus
from models.equipment import Equipment
from models.event_equipment_requirement import EventEquipmentRequirement
from models.event_request import EventRequest
from tests.integration.test_equipment_requirements import body, catalogue, planning_event, url
from tests.integration.test_submit_event_request import MakeClient, MakeUser

REVIEW_LIST = "/api/equipment-requirements/review"
OTHER_ROLES = ["organiser", "coordinator", "coordinator_lead", "venue_staff", "attendee"]


def review_url(requirement_id: object) -> str:
    return f"/api/equipment-requirements/{requirement_id}/review"


def requirement(
    db: Session, event: EventRequest, equipment_type: str = "Projector", **changes: Any
) -> EventEquipmentRequirement:
    now = datetime.now(UTC)
    values: dict[str, Any] = {
        "quantity": 2,
        "technical_requirements": "Needs an HDMI cable",
        "review_status": RequirementReview.PENDING_REVIEW,
        "created_at": now,
        "updated_at": now,
    }
    values.update(changes)
    row = EventEquipmentRequirement(
        event_request_id=event.id, equipment_type=equipment_type, **values
    )
    db.add(row)
    db.flush()
    return row


def stock(db: Session) -> list[tuple[uuid.UUID, int, bool]]:
    equipment = db.scalars(select(Equipment).order_by(Equipment.id))
    return [(e.id, e.total_quantity, e.is_active) for e in equipment]


def rows_for(response_json: list[dict[str, Any]], *events: EventRequest) -> list[dict[str, Any]]:
    ids = {str(event.id) for event in events}
    return [row for row in response_json if row["event_request_id"] in ids]


# --------------------------------------------------------------------------- AC1


@pytest.mark.story("SCRUM-44")
async def test_tech_support_sees_each_requirement_with_its_event_timing(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = planning_event(db, make_user)
    row = requirement(db, event)

    async with make_client(make_user("tech_support")) as client:
        response = await client.get(REVIEW_LIST)

    assert response.status_code == 200, response.text
    [listed] = rows_for(response.json(), event)
    assert listed["id"] == str(row.id)
    assert listed["event_name"] == event.name
    assert event.start_at is not None and event.end_at is not None
    assert datetime.fromisoformat(listed["event_start_at"]) == event.start_at
    assert datetime.fromisoformat(listed["event_end_at"]) == event.end_at
    assert listed["equipment_type"] == "Projector"
    assert listed["quantity"] == 2
    assert listed["technical_requirements"] == "Needs an HDMI cable"
    assert listed["review_status"] == "pending_review"


@pytest.mark.story("SCRUM-44")
async def test_the_list_holds_only_live_requirements_of_events_in_planning(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    planning, _ = planning_event(db, make_user)
    live = requirement(db, planning)
    requirement(db, planning, "Microphone", removed_at=datetime.now(UTC))
    confirmed, _ = planning_event(db, make_user)
    confirmed.status = EventStatus.CONFIRMED
    db.flush()
    requirement(db, confirmed)

    async with make_client(make_user("tech_support")) as client:
        response = await client.get(REVIEW_LIST)

    assert [row["id"] for row in rows_for(response.json(), planning, confirmed)] == [str(live.id)]


@pytest.mark.story("SCRUM-44")
async def test_the_soonest_event_is_listed_first(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    start = datetime.now(UTC) + timedelta(days=10)
    later, _ = planning_event(db, make_user, start_at=start, end_at=start + timedelta(hours=2))
    sooner, _ = planning_event(
        db, make_user, start_at=start - timedelta(days=1), end_at=start - timedelta(hours=22)
    )
    requirement(db, later)
    requirement(db, sooner)

    async with make_client(make_user("tech_support")) as client:
        response = await client.get(REVIEW_LIST)

    listed = [row["event_request_id"] for row in rows_for(response.json(), later, sooner)]
    assert listed == [str(sooner.id), str(later.id)]


@pytest.mark.story("SCRUM-44")
@pytest.mark.parametrize("role", OTHER_ROLES)
async def test_other_roles_cannot_list_requirements_for_review(
    make_user: MakeUser, make_client: MakeClient, role: str
) -> None:
    async with make_client(make_user(role)) as client:
        response = await client.get(REVIEW_LIST)

    assert response.status_code == 403


@pytest.mark.story("SCRUM-44")
async def test_anonymous_cannot_list_requirements_for_review(make_client: MakeClient) -> None:
    async with make_client(None) as client:
        response = await client.get(REVIEW_LIST)

    assert response.status_code == 401


# --------------------------------------------------------------------------- AC2


@pytest.mark.story("SCRUM-44")
@pytest.mark.parametrize("outcome", list(RequirementReview))
async def test_tech_support_records_each_outcome(
    db: Session, make_user: MakeUser, make_client: MakeClient, outcome: RequirementReview
) -> None:
    event, _ = planning_event(db, make_user)
    row = requirement(db, event, review_status=RequirementReview.UNAVAILABLE)

    async with make_client(make_user("tech_support")) as client:
        response = await client.patch(review_url(row.id), json={"review_status": outcome.value})

    assert response.status_code == 200, response.text
    assert response.json()["review_status"] == outcome.value
    db.refresh(row)
    assert row.review_status == outcome


@pytest.mark.story("SCRUM-44")
@pytest.mark.parametrize("payload", [{"review_status": "approved"}, {"review_status": None}, {}])
async def test_an_invalid_outcome_is_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient, payload: dict[str, Any]
) -> None:
    event, _ = planning_event(db, make_user)
    row = requirement(db, event)

    async with make_client(make_user("tech_support")) as client:
        response = await client.patch(review_url(row.id), json=payload)

    assert response.status_code == 422
    db.refresh(row)
    assert row.review_status == RequirementReview.PENDING_REVIEW


@pytest.mark.story("SCRUM-44")
async def test_a_missing_requirement_is_not_found(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("tech_support")) as client:
        response = await client.patch(review_url(uuid.uuid4()), json={"review_status": "available"})

    assert response.status_code == 404


@pytest.mark.story("SCRUM-44")
async def test_a_removed_requirement_is_not_found(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = planning_event(db, make_user)
    row = requirement(db, event, removed_at=datetime.now(UTC))

    async with make_client(make_user("tech_support")) as client:
        response = await client.patch(review_url(row.id), json={"review_status": "available"})

    assert response.status_code == 404


@pytest.mark.story("SCRUM-44")
@pytest.mark.parametrize(
    "status",
    [EventStatus.DRAFT, EventStatus.SUBMITTED, EventStatus.CONFIRMED, EventStatus.REJECTED],
)
async def test_a_requirement_outside_planning_cannot_be_reviewed(
    db: Session, make_user: MakeUser, make_client: MakeClient, status: EventStatus
) -> None:
    event, _ = planning_event(db, make_user)
    row = requirement(db, event)
    event.status = status
    db.flush()

    async with make_client(make_user("tech_support")) as client:
        response = await client.patch(review_url(row.id), json={"review_status": "available"})

    assert response.status_code == 409
    db.refresh(row)
    assert row.review_status == RequirementReview.PENDING_REVIEW


@pytest.mark.story("SCRUM-44")
@pytest.mark.parametrize("role", OTHER_ROLES)
async def test_other_roles_cannot_review(
    db: Session, make_user: MakeUser, make_client: MakeClient, role: str
) -> None:
    event, _ = planning_event(db, make_user)
    row = requirement(db, event)

    async with make_client(make_user(role)) as client:
        response = await client.patch(review_url(row.id), json={"review_status": "available"})

    assert response.status_code == 403
    db.refresh(row)
    assert row.review_status == RequirementReview.PENDING_REVIEW


@pytest.mark.story("SCRUM-44")
async def test_anonymous_cannot_review(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _ = planning_event(db, make_user)
    row = requirement(db, event)

    async with make_client(None) as client:
        response = await client.patch(review_url(row.id), json={"review_status": "available"})

    assert response.status_code == 401


# --------------------------------------------------------------------- AC3 and AC4


@pytest.mark.story("SCRUM-44")
async def test_the_coordinator_sees_the_review_and_a_change_invalidates_it(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # End to end through both routes: SCRUM-43's own AC5 test stands in for the review
    # by writing the column directly, which this story no longer needs to do.
    catalogue(db, "Projector")
    event, coordinator = planning_event(db, make_user)

    async with make_client(coordinator) as client:
        added = await client.post(url(event), json=body())
    requirement_id = added.json()["id"]
    async with make_client(make_user("tech_support")) as client:
        await client.patch(
            review_url(requirement_id), json={"review_status": "partially_available"}
        )
    async with make_client(coordinator) as client:
        seen = await client.get(url(event))
        changed = await client.patch(url(event, f"/{requirement_id}"), json={"quantity": 5})

    assert [row["review_status"] for row in seen.json()] == ["partially_available"]
    assert changed.json()["review_status"] == "pending_review"


# --------------------------------------------------------------------------- AC5


@pytest.mark.story("SCRUM-44")
async def test_reviewing_reserves_nothing(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    catalogue(db, "Projector")
    event, _ = planning_event(db, make_user)
    row = requirement(db, event, quantity=99)
    before = stock(db)

    async with make_client(make_user("tech_support")) as client:
        response = await client.patch(review_url(row.id), json={"review_status": "available"})

    assert response.status_code == 200, response.text
    db.expire_all()
    assert stock(db) == before
