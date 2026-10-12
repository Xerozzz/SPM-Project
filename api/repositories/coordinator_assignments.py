"""Persistence for coordinator assignment history (SCRUM-97).

Append-only: this module inserts history rows and lists them in deterministic
chronological order. Nothing here updates or deletes a history row — see ADR-0021.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.event_coordinator_assignment import EventCoordinatorAssignment


def list_for_event(db: Session, event_request_id: uuid.UUID) -> list[EventCoordinatorAssignment]:
    """A request's assignment history, oldest first with id as the stable tiebreak."""
    statement = (
        select(EventCoordinatorAssignment)
        .where(EventCoordinatorAssignment.event_request_id == event_request_id)
        .order_by(EventCoordinatorAssignment.assigned_at.asc(), EventCoordinatorAssignment.id.asc())
    )
    return list(db.scalars(statement))


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
