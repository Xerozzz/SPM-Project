"""Safety review persistence (SCRUM-79)."""

import uuid
from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.event_request import EventRequest
from models.safety_review import SafetyReview


def list_for_event(db: Session, event_request_id: uuid.UUID) -> list[SafetyReview]:
    """AC9: every decision on this event, oldest first.

    Ordered by `decided_at` then `id`, so two decisions saved in the same instant still
    come back in the same order every time and "the latest" has one answer.
    """
    statement = (
        select(SafetyReview)
        .where(SafetyReview.event_request_id == event_request_id)
        .order_by(SafetyReview.decided_at, SafetyReview.id)
    )
    return list(db.scalars(statement))


def latest_for_events(
    db: Session, event_request_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, SafetyReview]:
    """The newest decision for each of several events, keyed by event.

    One query rather than one per event: the worklist shows every event being planned, so
    asking per row would be an N+1 that grows with the board. Events never reviewed are
    absent, so callers use `.get(id)` rather than expecting a key.
    """
    if not event_request_ids:
        return {}
    statement = (
        select(SafetyReview)
        .where(SafetyReview.event_request_id.in_(event_request_ids))
        .order_by(SafetyReview.decided_at, SafetyReview.id)
    )
    # Later rows overwrite earlier ones, so what remains is each event's newest.
    return {row.event_request_id: row for row in db.scalars(statement)}


def reviewable_events(db: Session, status: str) -> list[EventRequest]:
    """AC1: the events a Safety Officer has a worklist for.

    Every event in planning, whether or not it is ready: AC2's prerequisites are shown as
    reasons on the screen, so an Officer can see what a Coordinator still owes them
    rather than wondering why an event is missing.
    """
    statement = (
        select(EventRequest)
        .where(EventRequest.status == status)
        .order_by(EventRequest.start_at, EventRequest.id)
    )
    return list(db.scalars(statement))


def save(db: Session, review: SafetyReview) -> SafetyReview:
    """Add a decision and commit it. Decisions are never updated, only added."""
    db.add(review)
    db.commit()
    db.refresh(review)
    return review
