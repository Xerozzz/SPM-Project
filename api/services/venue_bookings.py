"""Submit pending venue booking requests for approved events (SCRUM-38)."""

import uuid
from datetime import datetime

from core.database import Session
from domain import venue_suitability
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
