"""Event-review clarification orchestration for SCRUM-30."""

import uuid
from datetime import datetime

from core.database import Session
from domain.event_clarification import ClarificationKind
from models.event_clarification import EventClarification
from repositories import event_clarifications as repo


def list_for_event(db: Session, event_request_id: uuid.UUID) -> list[EventClarification]:
    """Return the retained clarification conversation for an authorized participant."""
    return repo.list_for_event(db, event_request_id)


def create_message(
    db: Session,
    event_request_id: uuid.UUID,
    author_id: uuid.UUID,
    kind: ClarificationKind,
    message: str,
    now: datetime,
) -> EventClarification:
    """Record one request or response without changing the event request's status.

    `kind` comes from the endpoint, not the caller's roles: the request endpoint is only
    reachable by the assigned coordinator and the response endpoint only by the owning
    organiser (core.dependencies.require_event_access), so the endpoint knows which side
    is speaking even when one person holds both roles.
    """
    clarification = EventClarification(
        event_request_id=event_request_id,
        author_id=author_id,
        kind=kind,
        message=message,
        created_at=now,
    )
    return repo.save(db, clarification)
