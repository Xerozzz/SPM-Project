"""SCRUM-113 API evidence for owner-controlled registration intake."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from domain.registration_intake import RegistrationIntakeError
from models.event_request import EventRequest
from models.user import User
from services import event_confirmations
from services import registration_intake as intake_service
from tests.integration.test_event_confirmation import ready_event
from tests.integration.test_submit_event_request import MakeClient, MakeUser


def confirmed_event(db: Session, make_user: MakeUser) -> tuple[EventRequest, User, User]:
    event, _, coordinator = ready_event(db, make_user)
    event_confirmations.confirm(db, event, coordinator.id, datetime.now(UTC))
    organiser = db.get(User, event.organiser_id)
    assert organiser is not None
    return event, organiser, coordinator


@pytest.mark.story("SCRUM-113")
async def test_owner_opens_then_extends_registration_and_coordinator_can_read(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, coordinator = confirmed_event(db, make_user)
    deadline = datetime.now(UTC) + timedelta(days=2)

    async with make_client(organiser) as client:
        opened = await client.post(
            f"/api/event-requests/{event.id}/registration/open",
            json={"closes_at": deadline.isoformat()},
        )
        extended = await client.post(
            f"/api/event-requests/{event.id}/registration/extend",
            json={"closes_at": (deadline + timedelta(days=1)).isoformat()},
        )
    async with make_client(coordinator) as client:
        visible = await client.get(f"/api/event-requests/{event.id}/registration")

    assert opened.status_code == 200
    assert opened.json()["intake_open"] is True
    assert extended.status_code == 200
    assert visible.status_code == 200
    assert datetime.fromisoformat(visible.json()["closes_at"]) == deadline + timedelta(days=1)


@pytest.mark.story("SCRUM-113")
async def test_non_owner_cannot_change_settings_but_dual_role_owner_can(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, coordinator = confirmed_event(db, make_user)
    other = make_user("organiser")
    deadline = datetime.now(UTC) + timedelta(days=2)

    async with make_client(other) as client:
        refused = await client.post(
            f"/api/event-requests/{event.id}/registration/open",
            json={"closes_at": deadline.isoformat()},
        )
    organiser.roles.append("coordinator")
    async with make_client(organiser) as client:
        allowed = await client.post(f"/api/event-requests/{event.id}/registration/open", json={})
    async with make_client(coordinator) as client:
        coordinator_refused = await client.post(
            f"/api/event-requests/{event.id}/registration/open", json={}
        )

    assert refused.status_code == 403
    assert allowed.status_code == 200
    assert coordinator_refused.status_code == 403


@pytest.mark.story("SCRUM-113")
async def test_invalid_extension_and_non_confirmed_open_leave_settings_unchanged(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, _ = confirmed_event(db, make_user)
    deadline = datetime.now(UTC) + timedelta(days=2)
    async with make_client(organiser) as client:
        await client.post(
            f"/api/event-requests/{event.id}/registration/open",
            json={"closes_at": deadline.isoformat()},
        )
        invalid = await client.post(
            f"/api/event-requests/{event.id}/registration/extend",
            json={"closes_at": (deadline - timedelta(hours=1)).isoformat()},
        )
    db.expire_all()
    stored = db.get(EventRequest, event.id)
    assert stored is not None and stored.registration_closes_at == deadline
    assert invalid.status_code == 409

    stored.status = EventStatus.APPROVED
    db.flush()
    async with make_client(organiser) as client:
        refused = await client.post(f"/api/event-requests/{event.id}/registration/open", json={})
    assert refused.status_code == 409


@pytest.mark.story("SCRUM-113")
def test_suspension_preserves_settings_and_blocks_intake_after_reconfirmation(
    db: Session, make_user: MakeUser
) -> None:
    event, _, _ = confirmed_event(db, make_user)
    now = datetime.now(UTC)
    event.registration_opened_at = now
    event.registration_closes_at = now + timedelta(days=1)
    db.flush()

    intake_service.suspend_intake(db, event.id, now)
    db.expire_all()
    stored = db.get(EventRequest, event.id)
    assert stored is not None
    assert stored.registration_closes_at == now + timedelta(days=1)
    assert stored.registration_suspended_at == now
    with pytest.raises(RegistrationIntakeError):
        intake_service.require_open_intake(stored, now + timedelta(minutes=1))
