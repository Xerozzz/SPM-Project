"""SCRUM-109 AC6: `require_event_access(CANCEL_VENUE_ARRANGEMENT)` on its own.

Only the event's current assigned Coordinator passes. The rule has no status pin, so the
service can explain a refusal for an event outside planning (AC7, AC9) rather than the
dependency hiding it behind a 403. The route's own tests repeat AC6 over HTTP.
"""

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.dependencies import EventAccess, require_event_access
from domain.event_status import EventStatus
from models.event_request import EventRequest
from models.user import User
from tests.integration.test_submit_event_request import MakeUser
from tests.integration.test_submit_venue_booking import approved_event

check = require_event_access(EventAccess.CANCEL_VENUE_ARRANGEMENT)


def claims(user: User) -> dict[str, object]:
    return {"sub": str(user.id), "roles": list(user.roles)}


def refused(event: EventRequest, user: User, db: Session) -> int:
    with pytest.raises(HTTPException) as caught:
        check(event.id, claims(user), db)
    return caught.value.status_code


@pytest.mark.story("SCRUM-109")
@pytest.mark.parametrize("status", list(EventStatus))
def test_the_assigned_coordinator_passes_in_any_status(
    status: EventStatus, db: Session, make_user: MakeUser
) -> None:
    """No status pin: the service, not the dependency, refuses outside planning."""
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator)
    event.status = status
    db.flush()

    assert check(event.id, claims(coordinator), db).id == event.id


@pytest.mark.story("SCRUM-109")
@pytest.mark.parametrize(
    "role",
    [
        "coordinator",
        "coordinator_lead",
        "venue_staff",
        "tech_support",
        "attendee",
        "organiser",
    ],
)
def test_anyone_but_the_assigned_coordinator_is_forbidden(
    role: str, db: Session, make_user: MakeUser
) -> None:
    """An unassigned Coordinator, a Lead, Venue Staff and the rest."""
    event = approved_event(db, make_user("organiser"), make_user("coordinator"))

    assert refused(event, make_user(role), db) == 403


@pytest.mark.story("SCRUM-109")
def test_the_owning_organiser_is_forbidden_even_with_a_coordinator_role(
    db: Session, make_user: MakeUser
) -> None:
    """Owning the event is not being its assignee."""
    owner = make_user("organiser", "coordinator")
    event = approved_event(db, owner, make_user("coordinator"))

    assert refused(event, owner, db) == 403


@pytest.mark.story("SCRUM-109")
def test_reassignment_moves_the_right_at_once(db: Session, make_user: MakeUser) -> None:
    """The outgoing Coordinator loses it and the incoming one gains it."""
    outgoing, incoming = make_user("coordinator"), make_user("coordinator")
    event = approved_event(db, make_user("organiser"), outgoing)
    event.coordinator_id = incoming.id
    db.flush()

    assert refused(event, outgoing, db) == 403
    assert check(event.id, claims(incoming), db).id == event.id


@pytest.mark.story("SCRUM-109")
def test_the_coordinator_id_without_the_coordinator_role_is_forbidden(
    db: Session, make_user: MakeUser
) -> None:
    """Being named on the event is not enough; the token must carry the role too."""
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator)

    with pytest.raises(HTTPException) as caught:
        check(event.id, {"sub": str(coordinator.id), "roles": ["organiser"]}, db)
    assert caught.value.status_code == 403


@pytest.mark.story("SCRUM-109")
def test_an_unknown_event_is_not_found(db: Session, make_user: MakeUser) -> None:
    with pytest.raises(HTTPException) as caught:
        check(uuid.uuid4(), claims(make_user("coordinator")), db)
    assert caught.value.status_code == 404
