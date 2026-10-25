"""Event cancellation request persistence (SCRUM-115)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.event_cancellation import RequestStatus
from models.event_cancellation_request import EventCancellationRequest


def requests_for_event(db: Session, event_request_id: uuid.UUID) -> list[EventCancellationRequest]:
    """Every request for one event, oldest first."""
    statement = (
        select(EventCancellationRequest)
        .where(EventCancellationRequest.event_request_id == event_request_id)
        .order_by(EventCancellationRequest.requested_at, EventCancellationRequest.id)
    )
    return list(db.scalars(statement))


def pending_for_event(db: Session, event_request_id: uuid.UUID) -> EventCancellationRequest | None:
    """The one pending request, if any. The caller already holds the event's lock."""
    statement = select(EventCancellationRequest).where(
        EventCancellationRequest.event_request_id == event_request_id,
        EventCancellationRequest.status == RequestStatus.PENDING,
    )
    return db.scalars(statement).first()


def add(db: Session, request: EventCancellationRequest) -> EventCancellationRequest:
    """Stage one request and flush it, without committing."""
    db.add(request)
    db.flush()
    return request
