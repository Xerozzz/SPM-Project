"""Venue-unavailability orchestration for SCRUM-62, with closure impact for SCRUM-81.

A closure is always recordable once it is valid, even over confirmed bookings and live
holds (SCRUM-81 AC1). Saving one works out which of those it affects, keeps a snapshot
of them, and notifies each affected event's assigned Coordinator, all in one commit
(AC8). Nothing is cancelled and no booking is changed (AC3). See ADR-0044. A Confirmed
event it affects goes back to planning in the same commit (SCRUM-132, ADR-0053).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from core.database import Session
from domain.booking_conflict import BookedPeriod
from domain.event_replanning import ReplanCause, needs_replanning
from domain.notifications import NotificationSource, NotificationType
from domain.validation import FieldProblem
from domain.venue_buffer import VenueBuffers
from domain.venue_closure_impact import affected_by_closure, impact_key
from domain.venue_unavailability import VenueUnavailabilityFields, validate_unavailability
from models.event_request import EventRequest
from models.venue import Venue
from models.venue_booking import VenueBooking
from models.venue_closure_impact import VenueClosureImpact
from models.venue_unavailability import VenueUnavailability
from repositories import event_requests as event_repo
from repositories import notifications as notification_repo
from repositories import venue_availability as booking_repo
from repositories import venue_closure_impacts as impact_repo
from repositories import venue_unavailabilities as repo
from services import venues
from services.event_replanning import return_to_planning


class VenueUnavailabilityError(Exception):
    """Base class for closures the service cannot perform."""


class VenueUnavailabilityNotFoundError(VenueUnavailabilityError):
    """The named closure does not exist at this venue."""


class InactiveVenueError(VenueUnavailabilityError):
    """New closure records only make sense for selectable venues."""


class InvalidVenueUnavailabilityError(VenueUnavailabilityError):
    def __init__(self, problems: list[FieldProblem]) -> None:
        super().__init__("the unavailability period is not valid")
        self.problems = problems


@dataclass(frozen=True)
class AffectedArrangement:
    """One live booking or hold a saved closure runs into, with its event."""

    booking: VenueBooking
    event: EventRequest | None


@dataclass(frozen=True)
class SavedClosure:
    """A saved closure and what it affected when it was saved (AC2)."""

    record: VenueUnavailability
    affected: list[AffectedArrangement]


def list_for_venue(db: Session, venue_id: uuid.UUID) -> list[VenueUnavailability]:
    venues.get(db, venue_id)
    return repo.list_for_venue(db, venue_id)


def create(
    db: Session,
    venue_id: uuid.UUID,
    fields: VenueUnavailabilityFields,
    staff_id: uuid.UUID,
    now: datetime,
) -> SavedClosure:
    venue = venues.get(db, venue_id)
    if not venue.is_active:
        raise InactiveVenueError
    _ensure_valid(fields, now)
    record = repo.stage(db, VenueUnavailability(venue_id=venue_id, **_stored_values(fields)))
    return _record_impact(db, venue, record, staff_id, now)


def update(
    db: Session,
    venue_id: uuid.UUID,
    unavailability_id: uuid.UUID,
    fields: VenueUnavailabilityFields,
    staff_id: uuid.UUID,
    now: datetime,
) -> SavedClosure:
    record = _get_for_venue(db, venue_id, unavailability_id)
    _ensure_valid(fields, now)
    for name, value in _stored_values(fields).items():
        setattr(record, name, value)
    repo.stage(db, record)
    # AC6: the impact is worked out again for the period the closure has now.
    return _record_impact(db, venues.get(db, venue_id), record, staff_id, now)


def delete(db: Session, venue_id: uuid.UUID, unavailability_id: uuid.UUID) -> None:
    repo.delete(db, _get_for_venue(db, venue_id, unavailability_id))


def _get_for_venue(
    db: Session, venue_id: uuid.UUID, unavailability_id: uuid.UUID
) -> VenueUnavailability:
    record = repo.get(db, unavailability_id)
    if record is None or record.venue_id != venue_id:
        raise VenueUnavailabilityNotFoundError
    return record


def _ensure_valid(fields: VenueUnavailabilityFields, now: datetime) -> None:
    problems = validate_unavailability(fields, now)
    if problems:
        raise InvalidVenueUnavailabilityError(problems)


def _stored_values(fields: VenueUnavailabilityFields) -> dict[str, object]:
    assert fields.starts_at is not None
    assert fields.ends_at is not None
    assert fields.reason is not None
    return {
        "starts_at": fields.starts_at,
        "ends_at": fields.ends_at,
        "reason": fields.reason.strip(),
    }


def _record_impact(
    db: Session,
    venue: Venue,
    record: VenueUnavailability,
    staff_id: uuid.UUID,
    now: datetime,
) -> SavedClosure:
    """AC2, AC4, AC7, AC8: find what the closure hits, keep a snapshot, notify, commit.

    The candidates are the same live set the problem displays use (SCRUM-89): confirmed
    bookings and unexpired holds still running at `now`. Pending requests are not
    commitments, so a closure over one is not an impact (SCRUM-62).
    """
    rows = {row.id: row for row in booking_repo.blocking_periods_from(db, venue.id, now)}
    buffers = VenueBuffers(
        setup_minutes=venue.setup_minutes, turnaround_minutes=venue.turnaround_minutes
    )
    hit = affected_by_closure(
        [
            BookedPeriod(id=row.id, status=row.status, start_at=row.start_at, end_at=row.end_at)
            for row in rows.values()
        ],
        record.starts_at,
        record.ends_at,
        buffers,
    )
    affected = [
        AffectedArrangement(rows[b.id], event_repo.get(db, rows[b.id].event_request_id))
        for b in hit
    ]
    if affected:
        impact_repo.stage(
            db,
            VenueClosureImpact(
                unavailability_id=record.id,
                venue_id=venue.id,
                recorded_by_id=staff_id,
                recorded_at=now,
                starts_at=record.starts_at,
                ends_at=record.ends_at,
                reason=record.reason,
                affected_booking_ids=[item.booking.id for item in affected],
            ),
        )
    for item in affected:
        # AC4: zero recipients is fine. An event with no Coordinator is still affected
        # and still shown to Venue Staff, it just has nobody to notify.
        if item.event is None or item.event.coordinator_id is None:
            continue
        notification_repo.stage(
            db,
            recipient_id=item.event.coordinator_id,
            event_request_id=item.event.id,
            type=NotificationType.VENUE_CLOSURE_IMPACT,
            source_type=NotificationSource.VENUE_CLOSURE,
            source_id=impact_key(record.id, record.starts_at, record.ends_at, item.booking.id),
            occurred_at=now,
        )
    _replan_confirmed(db, affected, record, now)
    db.commit()
    db.refresh(record)
    return SavedClosure(record=record, affected=affected)


def _replan_confirmed(
    db: Session, affected: list[AffectedArrangement], record: VenueUnavailability, now: datetime
) -> None:
    """SCRUM-132: return each affected Confirmed event to planning (ADR-0053).

    Each event once, however many of its arrangements the closure hits. Locked in id
    order and checked again on the locked row, so two closures never wait on each other
    in opposite orders, and a retry finds the event already in planning and leaves it.
    """
    event_ids = sorted({item.event.id for item in affected if item.event is not None})
    for event_id in event_ids:
        event = event_repo.get_for_update(db, event_id)
        if event is not None and needs_replanning(event.status):
            source = f"{record.id}|{record.starts_at.isoformat()}|{record.ends_at.isoformat()}"
            return_to_planning(db, event, ReplanCause.VENUE_CLOSURE, source, now)
