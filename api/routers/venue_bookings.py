"""Venue booking request endpoints: coordinators submit them (SCRUM-38) and venue staff
approve them (SCRUM-74, which absorbs SCRUM-40's approve action — see ADR-0017)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import EventAccess, require_event_access, require_role
from domain.booking_conflict import BookingConflictError
from domain.roles import Role
from domain.venue_booking import InvalidBookingTransitionError
from models.event_request import EventRequest
from schemas.event_requests import FieldProblemRead
from schemas.venue_bookings import (
    SuitabilityRead,
    VenueBookingCreate,
    VenueBookingRead,
    VenueBookingSubmissionRead,
)
from services import venue_bookings as service

router = APIRouter(prefix="/event-requests", tags=["venue-bookings"])
decisions = APIRouter(prefix="/venue-bookings", tags=["venue-bookings"])
PlanningEvent = Annotated[
    EventRequest, Depends(require_event_access(EventAccess.SUBMIT_VENUE_BOOKING))
]
Db = Annotated[Session, Depends(get_db)]
VenueStaff = Annotated[dict[str, object], Depends(require_role(Role.VENUE_STAFF))]


def _validation_error(exc: service.InvalidBookingRequestError) -> HTTPException:
    problems = [FieldProblemRead(field=p.field, reason=p.reason) for p in exc.problems]
    return HTTPException(422, [p.model_dump() for p in problems])


@router.get("/{request_id}/venue-bookings/suitability", response_model=SuitabilityRead)
def venue_suitability(event: PlanningEvent, venue_id: uuid.UUID, db: Db) -> SuitabilityRead:
    try:
        result = service.evaluate(db, event, venue_id, datetime.now(UTC))
    except service.InvalidBookingRequestError as exc:
        raise _validation_error(exc) from exc
    return SuitabilityRead.model_validate(result)


@router.post(
    "/{request_id}/venue-bookings",
    response_model=VenueBookingSubmissionRead,
    status_code=status.HTTP_201_CREATED,
)
def submit_venue_booking(
    event: PlanningEvent, body: VenueBookingCreate, db: Db
) -> VenueBookingSubmissionRead:
    try:
        booking, suitability = service.submit(db, event, body.venue_id, datetime.now(UTC))
    except service.InvalidBookingRequestError as exc:
        raise _validation_error(exc) from exc
    except service.PendingBookingExistsError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A pending booking request already exists"
        ) from exc
    return VenueBookingSubmissionRead(
        id=booking.id,
        venue_id=booking.venue_id,
        start_at=booking.start_at,
        end_at=booking.end_at,
        status=booking.status,
        suitability=SuitabilityRead.model_validate(suitability),
    )


@decisions.post("/{booking_id}/approve", response_model=VenueBookingRead)
def approve_venue_booking(booking_id: uuid.UUID, _: VenueStaff, db: Db) -> VenueBookingRead:
    """SCRUM-74 AC1/AC2: venue staff only; an overlapping or non-pending request is 409."""
    try:
        booking = service.approve(db, booking_id)
    except service.BookingNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Venue booking not found") from exc
    except (BookingConflictError, InvalidBookingTransitionError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return VenueBookingRead.model_validate(booking)
