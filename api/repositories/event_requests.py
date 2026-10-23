"""Event request queries. The only layer that touches the event_requests table (ADR-0003)."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from domain.coordinator_assignment import org_day_bounds
from domain.event_status import ACTIVE_STATUSES, EventStatus
from models.event_request import EventRequest
from models.user import User

# The Lead queue and overview show emails, not UUIDs: each row carries the
# organiser's email, and the overview also carries the current coordinator's
# email (None when unassigned). Joined here so services never touch SQLAlchemy.
UnassignedRow = tuple[EventRequest, str]
ActiveRow = tuple[EventRequest, str, str | None]


def get(db: Session, request_id: uuid.UUID) -> EventRequest | None:
    """Return the request with this id, or None."""
    return db.get(EventRequest, request_id)


def get_for_update(db: Session, request_id: uuid.UUID) -> EventRequest | None:
    """Return the request with this id, locked until the transaction ends.

    `with_for_update` issues SELECT ... FOR UPDATE even if the request is already in the
    identity map. `populate_existing` refreshes that in-memory object from the locked
    read, so a caller that waited for another transaction sees its committed changes.
    Together they serialise simultaneous submissions without a check-then-act race.
    """
    return db.get(EventRequest, request_id, with_for_update=True, populate_existing=True)


def list_for_organiser(db: Session, organiser_id: uuid.UUID) -> list[EventRequest]:
    """Every request this organiser owns, newest first."""
    statement = (
        select(EventRequest)
        .where(EventRequest.organiser_id == organiser_id)
        .order_by(EventRequest.created_at.desc())
    )
    return list(db.scalars(statement))


def list_submitted(db: Session) -> list[EventRequest]:
    """Submitted requests available for coordinator review, oldest first.

    Kept for callers that legitimately see every Submitted request (Lead allocation
    views). Coordinator review uses `list_submitted_for_coordinator` instead (SCRUM-104).
    """
    statement = (
        select(EventRequest)
        .where(EventRequest.status == EventStatus.SUBMITTED)
        .order_by(EventRequest.submitted_at.asc(), EventRequest.id.asc())
    )
    return list(db.scalars(statement))


def list_submitted_for_coordinator(db: Session, coordinator_id: uuid.UUID) -> list[EventRequest]:
    """SCRUM-104: Submitted requests currently assigned to this coordinator, oldest first.

    `id` is the stable secondary order for equal `submitted_at` values, matching the
    unscoped list. Unassigned requests and other coordinators' requests never appear.
    """
    statement = (
        select(EventRequest)
        .where(
            EventRequest.status == EventStatus.SUBMITTED,
            EventRequest.coordinator_id == coordinator_id,
        )
        .order_by(EventRequest.submitted_at.asc(), EventRequest.id.asc())
    )
    return list(db.scalars(statement))


def list_unassigned_submitted(db: Session) -> list[UnassignedRow]:
    """SCRUM-101: Submitted requests with no coordinator, oldest submission first.

    Only unassigned Submitted rows appear: assigned requests and requests outside the
    active review state are excluded. `id` is the stable secondary order for equal
    `submitted_at` values. Each row carries the organiser's email so the Lead sees a
    name, not a UUID.
    """
    organiser = aliased(User)
    statement = (
        select(EventRequest, organiser.email)
        .join(organiser, EventRequest.organiser_id == organiser.id)
        .where(
            EventRequest.status == EventStatus.SUBMITTED,
            EventRequest.coordinator_id.is_(None),
        )
        .order_by(EventRequest.submitted_at.asc(), EventRequest.id.asc())
    )
    return list(db.execute(statement).tuples())


def list_bookable_for_coordinator(db: Session, coordinator_id: uuid.UUID) -> list[EventRequest]:
    """Approved requests assigned to this coordinator for venue booking."""
    statement = (
        select(EventRequest)
        .where(
            EventRequest.status == EventStatus.APPROVED,
            EventRequest.coordinator_id == coordinator_id,
        )
        .order_by(EventRequest.start_at.asc(), EventRequest.id.asc())
    )
    return list(db.scalars(statement))


def list_confirmed_for_coordinator(db: Session, coordinator_id: uuid.UUID) -> list[EventRequest]:
    """Confirmed events whose current assigned Coordinator may read intake settings."""
    statement = (
        select(EventRequest)
        .where(
            EventRequest.status == EventStatus.CONFIRMED,
            EventRequest.coordinator_id == coordinator_id,
        )
        .order_by(EventRequest.start_at.asc(), EventRequest.id.asc())
    )
    return list(db.scalars(statement))


def list_confirmed(db: Session) -> list[EventRequest]:
    """Confirmed events; the registration service applies the time-sensitive intake guard."""
    statement = (
        select(EventRequest)
        .where(EventRequest.status == EventStatus.CONFIRMED)
        .order_by(EventRequest.start_at.asc(), EventRequest.id.asc())
    )
    return list(db.scalars(statement))


def list_active_for_lead(db: Session) -> list[ActiveRow]:
    """SCRUM-100: every active request with its current coordinator (or Unassigned).

    The active-status set comes from the domain layer (`ACTIVE_STATUSES`), so the
    repository never carries its own copy of the list. Current ownership is read from
    the request row itself — history (SCRUM-97) never feeds this field. Deterministic
    order: event start time, then id as the stable secondary key. Each row carries the
    organiser's email and the current coordinator's email (None when unassigned).
    """
    organiser = aliased(User)
    coordinator = aliased(User)
    statement = (
        select(EventRequest, organiser.email, coordinator.email)
        .join(organiser, EventRequest.organiser_id == organiser.id)
        .outerjoin(coordinator, EventRequest.coordinator_id == coordinator.id)
        .where(EventRequest.status.in_(ACTIVE_STATUSES))
        .order_by(EventRequest.start_at.asc(), EventRequest.id.asc())
    )
    return list(db.execute(statement).tuples())


def list_drafts_for_organiser(db: Session, organiser_id: uuid.UUID) -> list[EventRequest]:
    """SCRUM-112: this organiser's own drafts, newest first (ADR-0039)."""
    statement = (
        select(EventRequest)
        .where(
            EventRequest.organiser_id == organiser_id,
            EventRequest.status == EventStatus.DRAFT,
        )
        .order_by(EventRequest.created_at.desc())
    )
    return list(db.scalars(statement))


def list_calendar_for_organisation(db: Session, organisation_id: uuid.UUID) -> list[EventRequest]:
    """SCRUM-87: same-organisation events with usable date ranges.

    SCRUM-112 (ADR-0039): this is the only read organisation membership grants, and its
    callers expose only the calendar fields; it no longer mirrors event VIEW access.
    """
    statement = (
        select(EventRequest)
        .join(User, EventRequest.organiser_id == User.id)
        .where(
            User.organisation_id == organisation_id,
            EventRequest.start_at.is_not(None),
            EventRequest.end_at.is_not(None),
            EventRequest.end_at > EventRequest.start_at,
        )
        .order_by(EventRequest.start_at.asc(), EventRequest.id.asc())
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
