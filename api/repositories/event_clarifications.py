"""Persistence for internal coordinator clarification notes (SCRUM-106)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.event_clarification import EventClarification


def list_for_event(db: Session, event_request_id: uuid.UUID) -> list[EventClarification]:
    """Return an event's clarification history in deterministic chronological order."""
    statement = (
        select(EventClarification)
        .where(EventClarification.event_request_id == event_request_id)
        .order_by(EventClarification.created_at.asc(), EventClarification.id.asc())
    )
    return list(db.scalars(statement))


def save(db: Session, clarification: EventClarification) -> EventClarification:
    """Persist and reload one clarification message."""
    db.add(clarification)
    db.commit()
    db.refresh(clarification)
    return clarification
