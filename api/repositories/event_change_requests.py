"""Database access for significant-change requests (SCRUM-37)."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from models.event_change_request import EventChangeRequest

ONE_PER_SUBMISSION = "event_change_requests_one_per_submission"


class DuplicateSubmissionError(Exception):
    """The database refused a second request for the same submission key (AC8)."""


def get_by_submission(
    db: Session, event_request_id: uuid.UUID, submission_key: uuid.UUID
) -> EventChangeRequest | None:
    """The request a submit action already made, if any."""
    statement = (
        select(EventChangeRequest)
        .options(selectinload(EventChangeRequest.items))
        .where(
            EventChangeRequest.event_request_id == event_request_id,
            EventChangeRequest.submission_key == submission_key,
        )
    )
    return db.scalars(statement).first()


def list_for_event(db: Session, event_request_id: uuid.UUID) -> list[EventChangeRequest]:
    """An event's change requests with their items, newest first."""
    statement = (
        select(EventChangeRequest)
        .options(selectinload(EventChangeRequest.items))
        .where(EventChangeRequest.event_request_id == event_request_id)
        .order_by(EventChangeRequest.created_at.desc(), EventChangeRequest.id)
    )
    return list(db.scalars(statement))


def save(db: Session, change: EventChangeRequest) -> EventChangeRequest:
    """Commit a new request and its items together, or neither (AC4)."""
    db.add(change)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == ONE_PER_SUBMISSION:
            raise DuplicateSubmissionError from exc
        raise
    db.refresh(change)
    return change
