"""Submit pending venue booking requests for approved events (SCRUM-38), check
whether one can be approved without a conflict (SCRUM-73), and approve it safely under
concurrency (SCRUM-74, which also absorbs SCRUM-40's approve action — see ADR-0017)."""

import uuid
from datetime import datetime

from core.database import Session
from domain import venue_booking, venue_hold, venue_suitability
from domain.booking_conflict import BookedPeriod, UnavailablePeriod, ensure_no_conflict
from domain.event_request import (
    EQUIPMENT_REQUIREMENT_FACILITIES,
    EventRequestFields,
    field_names,
    validate_event_request,
)
from domain.validation import FieldProblem
from domain.venue_booking import BookingStatus
from domain.venue_buffer import VenueBuffers, effective_interval
from models.event_request import EventRequest
from models.venue import Venue
from models.venue_booking import VenueBooking
from repositories import equipment_requirements as requirement_repo
from repositories import event_requests as event_repo
from repositories import venue_availability as booking_repo
from repositories import venues as venue_repo
from services import venue_hold_expiry


class InvalidBookingRequestError(Exception):
    def __init__(self, problems: list[FieldProblem]) -> None:
        self.problems = problems


class BookingNotFoundError(Exception):
    """No venue booking has that id."""


class InvalidHoldError(Exception):
    """SCRUM-83: the hold's expiry is not acceptable, field by field."""

    def __init__(self, problems: list[FieldProblem]) -> None:
        super().__init__("invalid tentative hold")
        self.problems = problems


def evaluate(
    db: Session, event: EventRequest, venue_id: uuid.UUID, now: datetime
) -> venue_suitability.SuitabilityResult:
    venue = _validated_venue(db, event, venue_id, now)
    assert event.expected_attendance is not None
    required_facilities = _facilities_needed(db, event)
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


def _facilities_needed(db: Session, event: EventRequest) -> list[str]:
    """SCRUM-43: what the event's maintained requirements ask the venue to provide.

    Read from `event_equipment_requirements`, not from the organiser's
    `equipment_requirement` string. That column is the original submission and the
    Coordinator does not write back to it (ADR-0033), so once they add, change or remove
    anything the two disagree, and suitability was scoring the stale one. It also only
    ever named a single type, so an event needing three things was judged on one of them.

    `EQUIPMENT_REQUIREMENT_FACILITIES` still bridges the two vocabularies. Equipment types
    and venue facilities are separate lists (ADR-0031, ADR-0032): a venue offers a fixed
    projector, it does not offer the portable things that arrive from the store room. A
    requirement with no counterpart is therefore not a missing facility and is left
    unscored, exactly as it is today, rather than reported as something the venue lacks.
    """
    return [
        EQUIPMENT_REQUIREMENT_FACILITIES[requirement.equipment_type]
        for requirement in requirement_repo.list_for_event(db, event.id)
        if requirement.equipment_type in EQUIPMENT_REQUIREMENT_FACILITIES
    ]


def submit(
    db: Session, event: EventRequest, venue_id: uuid.UUID, now: datetime
) -> tuple[VenueBooking, venue_suitability.SuitabilityResult]:
    locked = event_repo.get_for_update(db, event.id)
    assert locked is not None and locked.coordinator_id is not None
    suitability = evaluate(db, locked, venue_id, now)
    assert locked.start_at is not None and locked.end_at is not None
    venue = venue_repo.get(db, venue_id)
    assert venue is not None  # evaluate() has already refused an unknown venue.
    effective_start, effective_end = effective_interval(
        locked.start_at, locked.end_at, _buffers(venue)
    )
    booking = VenueBooking(
        event_request_id=locked.id,
        venue_id=venue_id,
        requested_by_id=locked.coordinator_id,
        start_at=locked.start_at,
        end_at=locked.end_at,
        effective_start_at=effective_start,
        effective_end_at=effective_end,
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
    expires_at: datetime,
) -> VenueBooking:
    """SCRUM-110 (superseding SCRUM-74's direct confirmation and SCRUM-107's
    hold confirmation): approving a pending request places the SCRUM-83 tentative hold
    until `expires_at`, never a confirmation. Approval IS the hold, so this delegates
    to `hold()`: the same row lock, expiry validation, SCRUM-73 check, effective
    interval refresh and exclusion-constraint commit. Neither a Pending nor a Tentative
    row can become Confirmed through Venue Staff approval (AC4); SCRUM-80 owns the
    later event-confirmation step. SCRUM-75 AC2: the approving staff and UTC action
    time are stored as the hold's `held_by_id`/`held_at` in the same commit."""
    return hold(db, booking_id, decided_by_id, expires_at, decided_at)


def hold(
    db: Session,
    booking_id: uuid.UUID,
    held_by_id: uuid.UUID,
    expires_at: datetime,
    now: datetime,
) -> VenueBooking:
    """SCRUM-83 AC1: Venue Staff put a pending request on a tentative hold until
    `expires_at`. The request already names the venue, the event and its period, and was
    made by the event's assigned Coordinator, so the hold is for all of them (ADR-0029).

    The steps are approve's, because a hold occupies the venue the same way (AC3):
    lock the row and check the transition, check the expiry, run the SCRUM-73 check for a
    named refusal, refresh the effective interval from the venue's current buffers, and
    commit under the exclusion constraint, which covers tentative holds since 0021.
    """
    # SCRUM-108: holds that ran out stop blocking before anything is checked.
    venue_hold_expiry.expire_due_holds(db, now)
    booking = booking_repo.get_booking_for_update(db, booking_id)
    if booking is None:
        raise BookingNotFoundError
    held = venue_booking.hold(booking.status)
    problems = venue_hold.expiry_problems(expires_at, now, booking.start_at)
    if problems:
        raise InvalidHoldError(problems)
    _ensure_no_conflict(db, booking)
    venue = venue_repo.get(db, booking.venue_id)
    assert venue is not None
    booking.effective_start_at, booking.effective_end_at = effective_interval(
        booking.start_at, booking.end_at, _buffers(venue)
    )
    booking.status = held
    booking.expires_at = expires_at
    booking.held_by_id = held_by_id
    booking.held_at = now
    return booking_repo.save_confirmed_booking(db, booking)


def _buffers(venue: Venue) -> VenueBuffers:
    """SCRUM-82: the venue's current setup and turnaround, as the domain takes them."""
    return VenueBuffers(
        setup_minutes=venue.setup_minutes, turnaround_minutes=venue.turnaround_minutes
    )


def _ensure_no_conflict(db: Session, booking: VenueBooking) -> None:
    """SCRUM-82 AC4: the check compares effective occupied intervals.

    Buffers are read from the venue now rather than from the booking's stored effective
    columns, so a buffer change takes effect on the next check without touching any
    booking row. The stored columns exist only for the overlap constraint; ADR-0019 says
    why the two can differ and which story closes the gap.
    """
    venue = venue_repo.get(db, booking.venue_id)
    assert venue is not None  # a booking cannot exist without its venue (foreign key).
    others = [
        BookedPeriod(id=row.id, status=row.status, start_at=row.start_at, end_at=row.end_at)
        for row in booking_repo.other_bookings_overlapping(db, booking)
    ]
    closures = [
        UnavailablePeriod(id=row.id, starts_at=row.starts_at, ends_at=row.ends_at)
        for row in booking_repo.unavailabilities_overlapping(db, booking)
    ]
    ensure_no_conflict(booking.start_at, booking.end_at, others, closures, _buffers(venue))


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
