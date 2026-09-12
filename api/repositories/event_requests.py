"""Event request queries. The only layer that touches the event_requests table (ADR-0003)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.event_request import EventRequest


def get(db: Session, request_id: uuid.UUID) -> EventRequest | None:
    """Return the request with this id, or None."""
    return db.get(EventRequest, request_id)


def get_for_update(db: Session, request_id: uuid.UUID) -> EventRequest | None:
    """Return the request with this id, locked until the transaction ends.

    SELECT ... FOR UPDATE makes a second caller wait for the first to commit, then hands
    it the *committed* row — so two simultaneous submissions serialise: the second one
    sees status SUBMITTED and the state machine refuses it. Correctness comes from the
    database, not from a check-then-act in Python (same reasoning as ADR-0002).
    """
    return db.get(EventRequest, request_id, with_for_update=True)


def list_for_organiser(db: Session, organiser_id: uuid.UUID) -> list[EventRequest]:
    """Every request this organiser owns, newest first."""
    statement = (
        select(EventRequest)
        .where(EventRequest.organiser_id == organiser_id)
        .order_by(EventRequest.created_at.desc())
    )
    return list(db.scalars(statement))


def add(db: Session, request: EventRequest) -> EventRequest:
    """Stage a new request in the current transaction (no commit)."""
    db.add(request)
    return request


def save(db: Session, request: EventRequest) -> EventRequest:
    """Commit the request's pending changes and reload it with database-set values."""
    db.add(request)
    db.commit()
    db.refresh(request)
    return request


def delete(db: Session, request: EventRequest) -> None:
    """Remove a request. Used by the dev seed; no story deletes requests yet."""
    db.delete(request)
