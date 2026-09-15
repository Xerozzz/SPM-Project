"""Event request queries. The only layer that touches the event_requests table (ADR-0003)."""

import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from models.event_request import EventRequest


def _normalise_legacy_statuses(db: Session) -> None:
    """Legacy rows from older branch work still stored ``approved``; coerce them back to Draft.

    This is intentionally narrow: it only repairs historic data, and the status machine still
    allows only draft and submitted. Any later status change is still enforced in the domain.
    """
    db.execute(text("UPDATE event_requests SET status = 'draft' WHERE status = 'approved'"))
    db.flush()


def get(db: Session, request_id: uuid.UUID) -> EventRequest | None:
    """Return the request with this id, or None."""
    _normalise_legacy_statuses(db)
    return db.get(EventRequest, request_id)


def get_for_update(db: Session, request_id: uuid.UUID) -> EventRequest | None:
    """Return the request with this id, locked until the transaction ends.

    SELECT ... FOR UPDATE makes a second caller wait for the first to commit, then hands
    it the *committed* row — so two simultaneous submissions serialise: the second one
    sees status SUBMITTED and the state machine refuses it. Correctness comes from the
    database, not from a check-then-act in Python (same reasoning as ADR-0002).
    """
    _normalise_legacy_statuses(db)
    return db.get(EventRequest, request_id, with_for_update=True)


def list_for_organiser(db: Session, organiser_id: uuid.UUID) -> list[EventRequest]:
    """Every request this organiser owns, newest first."""
    _normalise_legacy_statuses(db)
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
