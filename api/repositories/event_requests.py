"""Event request queries. The only layer that touches the event_requests table (ADR-0003)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.event_request import EventRequest


def get(db: Session, request_id: uuid.UUID) -> EventRequest | None:
    """Return the request with this id, or None."""
    return db.get(EventRequest, request_id)


def list_for_organiser(db: Session, organiser_id: uuid.UUID) -> list[EventRequest]:
    """Every request this organiser owns, newest first."""
    statement = (
        select(EventRequest)
        .where(EventRequest.organiser_id == organiser_id)
        .order_by(EventRequest.created_at.desc())
    )
    return list(db.scalars(statement))
