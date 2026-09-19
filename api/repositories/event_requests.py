"""Event request queries. The only layer that touches the event_requests table (ADR-0003)."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.coordinator_assignment import org_day_bounds
from domain.event_status import EventStatus
from models.event_request import EventRequest
from models.user import User


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


def list_submitted(db: Session) -> list[EventRequest]:
    """Submitted requests available for coordinator review, oldest first."""
    statement = (
        select(EventRequest)
        .where(EventRequest.status == EventStatus.SUBMITTED)
        .order_by(EventRequest.submitted_at.asc(), EventRequest.id.asc())
    )
    return list(db.scalars(statement))


def list_drafts_for_organisation(db: Session, organisation_id: uuid.UUID) -> list[EventRequest]:
    """Drafts created by organisers in this organisation, newest first."""
    statement = (
        select(EventRequest)
        .join(User, EventRequest.organiser_id == User.id)
        .where(
            User.organisation_id == organisation_id,
            EventRequest.status == EventStatus.DRAFT,
        )
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


def last_assigned_coordinator_id(db: Session) -> uuid.UUID | None:
    """The coordinator assigned most recently, so rotation can resume after them
    (SCRUM-34)."""
    stmt = (
        select(EventRequest.coordinator_id)
        .where(
            EventRequest.coordinator_id.is_not(None),
            EventRequest.assigned_at.is_not(None),
        )
        .order_by(EventRequest.assigned_at.desc().nulls_last())
        .limit(1)
    )
    return db.scalars(stmt).first()


def coordinator_ids_confirmed_on(db: Session, moment: datetime) -> set[uuid.UUID]:
    """Coordinators already committed to a CONFIRMED event overlapping `moment`'s
    calendar day (SCRUM-34) — the round-robin conflict the ticket calls a
    "Confirmed" event. Uses interval overlap, not just start_at, so an event
    spanning midnight still counts (same half-open convention as ADR-0002)."""
    day_start, day_end = org_day_bounds(moment)
    stmt = select(EventRequest.coordinator_id).where(
        EventRequest.status == EventStatus.CONFIRMED,
        EventRequest.coordinator_id.is_not(None),
        EventRequest.start_at < day_end,
        EventRequest.end_at > day_start,
    )
    return set(db.scalars(stmt))
