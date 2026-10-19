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
from domain.venue_buffer import effective_interval
from models.event_request import EventRequest
from models.venue import Venue
from models.venue_booking import VenueBooking
from repositories import venues as venue_repo
from schemas.event_requests import FieldProblemRead
from schemas.venue_booking_decisions import ConflictRead, VenueBookingHold
from schemas.venue_bookings import (
    SuitabilityRead,
    VenueBookingCreate,
    VenueBookingRead,
    VenueBookingSubmissionRead,
)
from services import venue_bookings as service
from services import venue_buffer_review as buffer_review

router = APIRouter(prefix="/event-requests", tags=["venue-bookings"])
decisions = APIRouter(prefix="/venue-bookings", tags=["venue-bookings"])
PlanningEvent = Annotated[
    EventRequest, Depends(require_event_access(EventAccess.SUBMIT_VENUE_BOOKING))
]
Db = Annotated[Session, Depends(get_db)]
VenueStaff = Annotated[dict[str, object], Depends(require_role(Role.VENUE_STAFF))]


def _user_id(user: dict[str, object]) -> uuid.UUID:
    return uuid.UUID(str(user["sub"]))


def _validation_error(exc: service.InvalidBookingRequestError) -> HTTPException:
    problems = [FieldProblemRead(field=p.field, reason=p.reason) for p in exc.problems]
    return HTTPException(422, [p.model_dump() for p in problems])


@router.get("/{request_id}/venue-bookings", response_model=list[VenueBookingRead])
def list_venue_bookings(event: PlanningEvent, db: Db) -> list[VenueBookingRead]:
    """SCRUM-71: existing booking requests for this assigned approved event.

    SCRUM-89 AC4: each one also carries what it now clashes with, if anything, so the
    assigned Coordinator sees a booking needing attention on their own event rather than
    having to be told about it separately.
    """
    rows = service.list_for_event(db, event)
    problems = buffer_review.problems_by_booking(db, rows, datetime.now(UTC))
    # One lookup per venue, not per booking: an event's bookings are usually at the same
    # few venues, and the buffers have to come from the venue as it is now.
    venues: dict[uuid.UUID, Venue] = {}
    for row in rows:
        if row.venue_id not in venues:
            venue = venue_repo.get(db, row.venue_id)
            assert venue is not None  # a booking cannot exist without its venue.
            venues[row.venue_id] = venue
    return [_booking_read(row, venues[row.venue_id], problems.get(row.id)) for row in rows]


def _booking_read(
    row: VenueBooking, venue: Venue, problem: buffer_review.ReviewedBooking | None
) -> VenueBookingRead:
    buffers = buffer_review.buffers_of(venue)
    held_from, held_to = effective_interval(row.start_at, row.end_at, buffers)
    return VenueBookingRead(
        **VenueBookingRead.model_validate(row).model_dump(
            exclude={"conflict", "effective_start_at", "effective_end_at"}
        ),
        effective_start_at=held_from,
        effective_end_at=held_to,
        conflict=(
            ConflictRead.from_error(problem.conflict, buffer_review.buffers_of(problem.venue))
            if problem is not None
            else None
        ),
    )


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
    return VenueBookingSubmissionRead(
        id=booking.id,
        venue_id=booking.venue_id,
        start_at=booking.start_at,
        end_at=booking.end_at,
        status=booking.status,
        suitability=SuitabilityRead.model_validate(suitability),
    )


@decisions.post("/{booking_id}/approve", response_model=VenueBookingRead)
def approve_venue_booking(
    booking_id: uuid.UUID, body: VenueBookingHold, user: VenueStaff, db: Db
) -> VenueBookingRead:
    """SCRUM-110: approval creates a time-limited tentative hold (AC1/AC2), never a
    confirmation. A bad expiry is 422, an overlapping or non-pending request 409.
    Records which staff member approved, and when, as the hold's actor and time."""
    try:
        booking = service.approve(
            db, booking_id, _user_id(user), datetime.now(UTC), body.expires_at
        )
    except service.BookingNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Venue booking not found") from exc
    except service.InvalidHoldError as exc:
        problems = [FieldProblemRead(field=p.field, reason=p.reason) for p in exc.problems]
        raise HTTPException(422, [p.model_dump() for p in problems]) from exc
    except (BookingConflictError, InvalidBookingTransitionError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    venue = venue_repo.get(db, booking.venue_id)
    assert venue is not None  # a booking cannot exist without its venue.
    # Through `_booking_read` like the listing, so `effective_*` means the same thing on
    # both routes. `model_validate` alone would have returned the stored snapshot here
    # and the derived period there, which is the field meaning two things at once.
    return _booking_read(booking, venue, None)
