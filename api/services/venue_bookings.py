"""Submit pending venue booking requests for approved events (SCRUM-38), check
whether one can be approved without a conflict (SCRUM-73), and approve it safely under
concurrency (SCRUM-74, which also absorbs SCRUM-40's approve action — see ADR-0017)."""

import uuid
from datetime import datetime

from core.database import Session
from domain import venue_booking, venue_suitability
from domain.booking_conflict import BookedPeriod, UnavailablePeriod, ensure_no_conflict
from domain.event_request import (
    EQUIPMENT_REQUIREMENT_FACILITIES,
    EventRequestFields,
    field_names,
    validate_event_request,
)
from domain.validation import FieldProblem
from domain.venue_booking import BookingStatus
from models.event_request import EventRequest
from models.venue import Venue
from models.venue_booking import VenueBooking
from repositories import event_requests as event_repo
from repositories import venue_availability as booking_repo
from repositories import venues as venue_repo


class InvalidBookingRequestError(Exception):
    def __init__(self, problems: list[FieldProblem]) -> None:
        self.problems = problems


class PendingBookingExistsError(Exception):
    pass


class BookingNotFoundError(Exception):
    """No venue booking has that id."""


def evaluate(
    db: Session, event: EventRequest, venue_id: uuid.UUID, now: datetime
) -> venue_suitability.SuitabilityResult:
    venue = _validated_venue(db, event, venue_id, now)
    assert event.expected_attendance is not None
    equipment = event.equipment_requirement
    required_facilities = (
        [EQUIPMENT_REQUIREMENT_FACILITIES[equipment]] if equipment is not None else []
    )
    # `venue_requirement` is retained as event context, but Venue has no comparable
    # venue-type field yet. SCRUM-38 therefore cannot include it in suitability scoring.
    return venue_suitability.evaluate_suitability(
        venue_suitability.SuitabilityEvent(
            expected_attendance=event.expected_attendance,
            required_facilities=required_facilities,
            accessibility_need=event.accessibility_requirement,
            layout_need=event.layout_requirement,
        ),
        venue_suitability.SuitabilityVenue(
            maximum_capacity=venue.maximum_capacity,
            facilities=venue.facilities,
            accessibility_features=venue.accessibility_features,
            supported_layouts=venue.supported_layouts,
        ),
    )


def submit(
    db: Session, event: EventRequest, venue_id: uuid.UUID, now: datetime
) -> tuple[VenueBooking, venue_suitability.SuitabilityResult]:
    locked = event_repo.get_for_update(db, event.id)
    assert locked is not None and locked.coordinator_id is not None
    if booking_repo.pending_for_event(db, locked.id) is not None:
        raise PendingBookingExistsError
    suitability = evaluate(db, locked, venue_id, now)
    assert locked.start_at is not None and locked.end_at is not None
    booking = VenueBooking(
        event_request_id=locked.id,
        venue_id=venue_id,
        requested_by_id=locked.coordinator_id,
        start_at=locked.start_at,
        end_at=locked.end_at,
        status=BookingStatus.PENDING,
    )
    return booking_repo.save_booking(db, booking), suitability


def list_for_event(db: Session, event: EventRequest) -> list[VenueBooking]:
    """SCRUM-71: read retained booking requests for an approved assigned event."""
    return booking_repo.list_bookings_for_event(db, event.id)


def check_approvable(db: Session, booking_id: uuid.UUID) -> VenueBooking:
    """SCRUM-73: raise a `domain.booking_conflict.BookingConflictError` naming whatever
    blocks approving this booking, or return it if nothing does.

    A read-only preview: it neither locks nor changes status. `approve` runs the same
    check on a locked row, and the exclusion constraint backs it up (ADR-0002, ADR-0017).
    """
    booking = booking_repo.get_booking(db, booking_id)
    if booking is None:
        raise BookingNotFoundError
    _ensure_no_conflict(db, booking)
    return booking


def approve(
    db: Session,
    booking_id: uuid.UUID,
    decided_by_id: uuid.UUID,
    decided_at: datetime,
) -> VenueBooking:
    """SCRUM-74 (absorbs SCRUM-40's approve action): confirm a pending booking request.
    SCRUM-75 AC2: who approved and when are stored with the confirmation in the same
    commit (ADR-0018). Both are required, so no approve path can leave them empty.

    1. Lock the booking row, so two staff approving the same request take turns and the
       second is refused by the status transition (checked first, so a booking that is
       not pending is reported as such rather than as a conflict).
    2. Run the SCRUM-73 check, for a named, friendly refusal in the common case.
    3. Commit. If an overlapping request was approved concurrently and the check raced,
       the exclusion constraint refuses the commit (ConcurrentBookingConflictError).
    """
    booking = booking_repo.get_booking_for_update(db, booking_id)
    if booking is None:
        raise BookingNotFoundError
    confirmed = venue_booking.approve(booking.status)
    _ensure_no_conflict(db, booking)
    booking.status = confirmed
    booking.decided_by_id = decided_by_id
    booking.decided_at = decided_at
    return booking_repo.save_confirmed_booking(db, booking)


def _ensure_no_conflict(db: Session, booking: VenueBooking) -> None:
    others = [
        BookedPeriod(id=row.id, status=row.status, start_at=row.start_at, end_at=row.end_at)
        for row in booking_repo.other_bookings_overlapping(db, booking)
    ]
    closures = [
        UnavailablePeriod(id=row.id, starts_at=row.starts_at, ends_at=row.ends_at)
        for row in booking_repo.unavailabilities_overlapping(db, booking)
    ]
    ensure_no_conflict(booking.start_at, booking.end_at, others, closures)


def _validated_venue(db: Session, event: EventRequest, venue_id: uuid.UUID, now: datetime) -> Venue:
    fields = EventRequestFields(**{name: getattr(event, name) for name in field_names()})
    problems = validate_event_request(fields, now)
    venue = venue_repo.get(db, venue_id)
    if venue is None:
        problems.append(FieldProblem("venue_id", "does not identify a venue"))
    elif not venue.is_active:
        problems.append(FieldProblem("venue_id", "must identify an active venue"))
    if problems:
        raise InvalidBookingRequestError(problems)
    assert venue is not None
    return venue
