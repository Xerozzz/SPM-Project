"""Coordinator venue booking request endpoints (SCRUM-38)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import EventAccess, require_event_access
from models.event_request import EventRequest
from schemas.event_requests import FieldProblemRead
from schemas.venue_bookings import SuitabilityRead, VenueBookingCreate, VenueBookingSubmissionRead
from services import venue_bookings as service

router = APIRouter(prefix="/event-requests", tags=["venue-bookings"])
PlanningEvent = Annotated[
    EventRequest, Depends(require_event_access(EventAccess.SUBMIT_VENUE_BOOKING))
]
Db = Annotated[Session, Depends(get_db)]


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
        status=booking.status,
        suitability=SuitabilityRead.model_validate(suitability),
    )
