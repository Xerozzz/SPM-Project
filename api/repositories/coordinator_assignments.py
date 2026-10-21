"""Persistence for coordinator assignment history (SCRUM-97).

Append-only: this module inserts history rows and lists them in deterministic
chronological order. Nothing here updates or deletes a history row — see ADR-0021.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from models.event_coordinator_assignment import EventCoordinatorAssignment
from models.user import User

# SCRUM-105: an entry with the previous coordinator's, new coordinator's and acting
# Lead's emails, in that order. An email is None when its user row is missing.
HistoryRow = tuple[EventCoordinatorAssignment, str | None, str | None, str | None]


def list_for_event(db: Session, event_request_id: uuid.UUID) -> list[EventCoordinatorAssignment]:
    """A request's assignment history, oldest first with id as the stable tiebreak."""
    statement = (
        select(EventCoordinatorAssignment)
        .where(EventCoordinatorAssignment.event_request_id == event_request_id)
        .order_by(EventCoordinatorAssignment.assigned_at.asc(), EventCoordinatorAssignment.id.asc())
    )
    return list(db.scalars(statement))


def list_for_event_with_emails(db: Session, event_request_id: uuid.UUID) -> list[HistoryRow]:
    """SCRUM-105: `list_for_event` with each person's email, in the same order.

    LEFT joins, not inner: a missing user row must still show the entry (as an unknown
    user), never drop it from the audit trail. `list_for_event` stays as it is for the
    SCRUM-102 notifications that read plain rows.
    """
    previous = aliased(User)
    new = aliased(User)
    acted_by = aliased(User)
    statement = (
        select(EventCoordinatorAssignment, previous.email, new.email, acted_by.email)
        .outerjoin(previous, EventCoordinatorAssignment.previous_coordinator_id == previous.id)
        .outerjoin(new, EventCoordinatorAssignment.new_coordinator_id == new.id)
        .outerjoin(acted_by, EventCoordinatorAssignment.acted_by_id == acted_by.id)
        .where(EventCoordinatorAssignment.event_request_id == event_request_id)
        .order_by(EventCoordinatorAssignment.assigned_at.asc(), EventCoordinatorAssignment.id.asc())
    )
    return list(db.execute(statement).tuples())


def count_for_event(db: Session, event_request_id: uuid.UUID) -> int:
    """How many history rows a request has — used to assert "exactly one was added"."""
    statement = select(EventCoordinatorAssignment).where(
        EventCoordinatorAssignment.event_request_id == event_request_id
    )
    return len(list(db.scalars(statement)))


def append(
    db: Session,
    event_request_id: uuid.UUID,
    previous_coordinator_id: uuid.UUID | None,
    new_coordinator_id: uuid.UUID,
    acted_by_id: uuid.UUID,
    assigned_at: datetime,
) -> EventCoordinatorAssignment:
    """Stage one immutable history entry in the current transaction (no commit)."""
    entry = EventCoordinatorAssignment(
        event_request_id=event_request_id,
        previous_coordinator_id=previous_coordinator_id,
        new_coordinator_id=new_coordinator_id,
        acted_by_id=acted_by_id,
        assigned_at=assigned_at,
    )
    db.add(entry)
    return entry
