"""Event-review clarification orchestration for SCRUM-106."""

import uuid
from datetime import datetime

from core.database import Session
from domain.event_clarification import ClarificationKind
from models.event_clarification import EventClarification
from repositories import event_clarifications as repo


def list_for_event(db: Session, event_request_id: uuid.UUID) -> list[EventClarification]:
    """Return the internal notes for the currently assigned coordinator."""
    return repo.list_for_event(db, event_request_id)


def create_message(
    db: Session,
    event_request_id: uuid.UUID,
    author_id: uuid.UUID,
    kind: ClarificationKind,
    message: str,
    now: datetime,
) -> EventClarification:
    """Record one internal coordinator note without changing the event request's status.

    `kind` comes from the endpoint, not the caller's roles: only the internal-note
    endpoint is reachable, and only by the assigned coordinator
    (core.dependencies.require_event_access), so the endpoint knows who is speaking
    even when one person holds both roles.
    """
    clarification = EventClarification(
        event_request_id=event_request_id,
        author_id=author_id,
        kind=kind,
        message=message,
        created_at=now,
    )
    return repo.save(db, clarification)
