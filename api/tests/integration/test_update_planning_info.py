"""SCRUM-36: the assigned coordinator views and updates ordinary event planning information."""

import uuid
from collections.abc import Mapping

import httpx
import pytest
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from models.event_request import EventRequest
from models.user import User
from services import event_requests as service
from tests.integration.test_submit_event_request import (
    MakeClient,
    MakeUser,
    content_of,
    make_draft,
)


async def _submitted_and_assigned(
    db: Session, make_client: MakeClient, organiser: User, coordinator: User
) -> EventRequest:
    """A request submitted through the API and owned by `coordinator`.

    SCRUM-101 leaves a submission unassigned, and the Lead's assignment has its own tests,
    so ownership is arranged directly here, as the SCRUM-31 tests do.
    """
    request = make_draft(db, organiser)
    async with make_client(organiser) as client:
        response = await client.post(f"/api/event-requests/{request.id}/submit")
    assert response.status_code == 200
    request.coordinator_id = coordinator.id
    db.flush()
    return request


async def _update(
    client: httpx.AsyncClient, request_id: object, body: Mapping[str, object]
) -> httpx.Response:
    return await client.patch(f"/api/event-requests/{request_id}/planning-info", json=body)


# --------------------------------------------------------------------------- AC1, AC2


@pytest.mark.story("SCRUM-36")
async def test_assigned_coordinator_updates_ordinary_planning_information(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = await _submitted_and_assigned(db, make_client, organiser, coordinator)

    async with make_client(coordinator) as client:
        response = await _update(
            client,
            request.id,
            {"name": "Orientation Night", "layout_requirement": "Banquet style"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Orientation Night"
    assert body["layout_requirement"] == "Banquet style"
    # Fields that were not sent are left as they were, and the status does not move.
    assert body["purpose"] == "Welcome new students"
    assert body["status"] == "submitted"
    db.refresh(request)
    assert request.name == "Orientation Night"
    assert request.layout_requirement == "Banquet style"
    assert request.status is EventStatus.SUBMITTED


@pytest.mark.story("SCRUM-36")
async def test_every_ordinary_field_can_be_updated(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = await _submitted_and_assigned(db, make_client, organiser, coordinator)
    changes = {
        "name": "Orientation Night",
        "purpose": "Welcome and induct new students",
        "description": "Evening programme with talks.",
        "accessibility_requirement": "Step-free access",
        "layout_requirement": "Banquet style",
        "registration_requirement": "Invite only",
    }

    async with make_client(coordinator) as client:
        response = await _update(client, request.id, changes)

    assert response.status_code == 200
    db.refresh(request)
    for name, value in changes.items():
        assert getattr(request, name) == value


@pytest.mark.story("SCRUM-36")
async def test_the_organiser_sees_the_coordinators_update(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = await _submitted_and_assigned(db, make_client, organiser, coordinator)
    async with make_client(coordinator) as client:
        assert (await _update(client, request.id, {"purpose": "New purpose"})).status_code == 200

    async with make_client(organiser) as client:
        viewed = await client.get(f"/api/event-requests/{request.id}")

    # AC1: viewing goes through the existing require_event_access(VIEW).
    assert viewed.status_code == 200
    assert viewed.json()["purpose"] == "New purpose"


@pytest.mark.story("SCRUM-36")
async def test_ordinary_update_is_allowed_on_an_approved_request(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = await _submitted_and_assigned(db, make_client, organiser, coordinator)
    async with make_client(coordinator) as client:
        assert (await client.post(f"/api/event-requests/{request.id}/approve")).status_code == 200
        response = await _update(client, request.id, {"registration_requirement": "Invite only"})

    assert response.status_code == 200
    assert response.json()["registration_requirement"] == "Invite only"
    assert response.json()["status"] == "approved"


@pytest.mark.story("SCRUM-36")
async def test_ordinary_update_is_allowed_on_a_confirmed_request(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = await _submitted_and_assigned(db, make_client, organiser, coordinator)
    # No story moves a request into CONFIRMED yet, so the test arranges it directly, as
    # the SCRUM-34 tests do.
    request.status = EventStatus.CONFIRMED
    db.flush()

    async with make_client(coordinator) as client:
        response = await _update(client, request.id, {"description": "Updated programme"})

    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


@pytest.mark.story("SCRUM-36")
async def test_an_empty_update_changes_nothing(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = await _submitted_and_assigned(db, make_client, organiser, coordinator)
    before = content_of(request)

    async with make_client(coordinator) as client:
        response = await _update(client, request.id, {})

    assert response.status_code == 200
    db.refresh(request)
    assert content_of(request) == before


@pytest.mark.story("SCRUM-36")
async def test_an_ordinary_field_cannot_be_blanked(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = await _submitted_and_assigned(db, make_client, organiser, coordinator)
    before = content_of(request)

    async with make_client(coordinator) as client:
        response = await _update(client, request.id, {"description": "  ", "name": "Renamed"})

    # Validation failure: the whole update is refused, including the valid name.
    assert response.status_code == 422
    assert response.json()["detail"] == [{"field": "description", "reason": "is required"}]
    db.refresh(request)
    assert content_of(request) == before


# --------------------------------------------------------------------------- AC3


@pytest.mark.story("SCRUM-36")
@pytest.mark.parametrize(
    "protected",
    [
        {"start_at": "2030-01-01T02:00:00Z"},
        {"end_at": "2030-01-01T06:00:00Z"},
        {"expected_attendance": 50},
        {"venue_requirement": "Hall A"},
        {"equipment_requirement": "Projector"},
    ],
)
async def test_date_attendance_venue_and_equipment_cannot_change_through_this_flow(
    protected: dict[str, object],
    db: Session,
    make_user: MakeUser,
    make_client: MakeClient,
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = await _submitted_and_assigned(db, make_client, organiser, coordinator)
    before = content_of(request)

    async with make_client(coordinator) as client:
        # An allowed field rides along, to prove the whole update is refused, not part of it.
        response = await _update(client, request.id, {"name": "Renamed", **protected})

    assert response.status_code == 422
    db.refresh(request)
    assert content_of(request) == before


# --------------------------------------------------------------------------- AC4


@pytest.mark.story("SCRUM-36")
@pytest.mark.parametrize(
    "who", ["owning_organiser", "other_coordinator", "venue_staff", "lead", "attendee"]
)
async def test_users_without_permission_are_refused_and_the_request_is_unchanged(
    who: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = await _submitted_and_assigned(db, make_client, organiser, coordinator)
    before = content_of(request)
    callers = {
        # After submission the organiser asks the coordinator for changes instead.
        "owning_organiser": organiser,
        "other_coordinator": make_user("coordinator"),
        "venue_staff": make_user("venue_staff"),
        "lead": make_user("coordinator_lead"),
        "attendee": make_user("attendee"),
    }

    async with make_client(callers[who]) as client:
        response = await _update(client, request.id, {"name": "Hijacked"})

    assert response.status_code == 403
    db.refresh(request)
    assert content_of(request) == before


@pytest.mark.story("SCRUM-36")
async def test_the_shared_dependency_refuses_before_the_body_is_read(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC4 is enforced by require_event_access(UPDATE_PLANNING_INFO), not only by the
    service. The dependency runs before the body is validated, so a caller who may not
    update gets 403 even when the body would also have been refused with 422."""
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = await _submitted_and_assigned(db, make_client, organiser, coordinator)

    async with make_client(make_user("coordinator")) as client:
        response = await _update(client, request.id, {"expected_attendance": 50})

    assert response.status_code == 403


@pytest.mark.story("SCRUM-36")
async def test_the_shared_dependency_refuses_a_request_that_is_no_longer_active(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = await _submitted_and_assigned(db, make_client, organiser, coordinator)
    async with make_client(coordinator) as client:
        rejected = await client.post(
            f"/api/event-requests/{request.id}/reject", json={"reason": "Too large"}
        )
        response = await _update(client, request.id, {"expected_attendance": 50})

    assert rejected.status_code == 200
    assert response.status_code == 403


@pytest.mark.story("SCRUM-36")
async def test_a_signed_out_user_is_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = await _submitted_and_assigned(db, make_client, organiser, coordinator)

    async with make_client(None) as client:
        response = await _update(client, request.id, {"name": "Hijacked"})

    assert response.status_code == 401


@pytest.mark.story("SCRUM-36")
async def test_an_unassigned_submitted_request_cannot_be_updated(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = make_draft(db, organiser)
    async with make_client(organiser) as client:
        assert (await client.post(f"/api/event-requests/{request.id}/submit")).status_code == 200

    async with make_client(coordinator) as client:
        response = await _update(client, request.id, {"name": "Renamed"})

    assert response.status_code == 403


@pytest.mark.story("SCRUM-36")
async def test_a_draft_is_the_organisers_to_edit_not_the_coordinators(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = make_draft(db, organiser, coordinator_id=coordinator.id)

    async with make_client(coordinator) as client:
        response = await _update(client, request.id, {"name": "Renamed"})

    assert response.status_code == 403


@pytest.mark.story("SCRUM-36")
async def test_a_rejected_request_is_the_organisers_to_revise_not_the_coordinators(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = await _submitted_and_assigned(db, make_client, organiser, coordinator)
    async with make_client(coordinator) as client:
        rejected = await client.post(
            f"/api/event-requests/{request.id}/reject", json={"reason": "Too large"}
        )
        response = await _update(client, request.id, {"name": "Renamed"})

    assert rejected.status_code == 200
    assert response.status_code == 403
    db.refresh(request)
    assert request.name == "Orientation Day"


@pytest.mark.story("SCRUM-36")
async def test_an_unknown_request_is_not_found(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("coordinator")) as client:
        response = await _update(client, uuid.uuid4(), {"name": "Renamed"})

    assert response.status_code == 404


# ------------------------------------------- the service re-checks on the locked row


@pytest.mark.story("SCRUM-36")
async def test_a_request_reassigned_after_the_access_check_is_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = await _submitted_and_assigned(db, make_client, organiser, coordinator)
    # Another coordinator takes over between the dependency check and the update.
    request.coordinator_id = make_user("coordinator").id
    db.flush()

    with pytest.raises(service.NotAuthorisedError):
        service.update_planning_info(db, request.id, coordinator.id, {"name": "Renamed"})
    db.refresh(request)
    assert request.name == "Orientation Day"


@pytest.mark.story("SCRUM-36")
async def test_a_request_rejected_after_the_access_check_is_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    organiser = make_user("organiser")
    coordinator = make_user("coordinator")
    request = await _submitted_and_assigned(db, make_client, organiser, coordinator)
    request.status = EventStatus.REJECTED
    db.flush()

    with pytest.raises(service.NotAuthorisedError):
        service.update_planning_info(db, request.id, coordinator.id, {"name": "Renamed"})


@pytest.mark.story("SCRUM-36")
def test_the_service_reports_an_unknown_request(db: Session) -> None:
    with pytest.raises(service.EventRequestNotFoundError):
        service.update_planning_info(db, uuid.uuid4(), uuid.uuid4(), {"name": "Renamed"})
