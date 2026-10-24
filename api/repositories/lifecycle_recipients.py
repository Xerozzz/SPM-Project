"""Who to notify about an event's lifecycle (SCRUM-50). Reads only."""

import uuid
from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.registration import LIVE_STATUSES
from domain.roles import Role
from models.event_registration import EventRegistration
from models.user import User


def live_attendees(db: Session, event_request_id: uuid.UUID) -> set[uuid.UUID]:
    """AC5: attendees holding a Pending, Waitlisted or Accepted registration."""
    statement = select(EventRegistration.attendee_id).where(
        EventRegistration.event_request_id == event_request_id,
        EventRegistration.status.in_([status.value for status in LIVE_STATUSES]),
    )
    return set(db.scalars(statement))


def active_safety_officers(db: Session) -> set[uuid.UUID]:
    """AC2: the review team, resolved from active role holders."""
    statement = select(User.id).where(
        User.roles.contains([Role.SAFETY_OFFICER.value]), User.is_active.is_(True)
    )
    return set(db.scalars(statement))


def roles_of(db: Session, user_ids: Collection[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    """The roles of these users, active accounts only."""
    if not user_ids:
        return {}
    statement = select(User.id, User.roles).where(
        User.id.in_(list(user_ids)), User.is_active.is_(True)
    )
    return {row.id: list(row.roles) for row in db.execute(statement)}
