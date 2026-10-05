"""Venue Staff endpoints to review and reject venue booking requests (SCRUM-40).

Approve is on the same /venue-bookings prefix but lives in routers/venue_bookings.py
(the `decisions` router from SCRUM-74, ADR-0017). Both are registered in main.py.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import require_role
from domain.roles import Role
from domain.venue_booking import InvalidBookingTransitionError
from schemas.venue_booking_decisions import VenueBookingDecisionRead, VenueBookingReject
from services import venue_booking_decisions as service

router = APIRouter(prefix="/venue-bookings", tags=["venue-booking-decisions"])

VenueStaff = Annotated[dict[str, object], Depends(require_role(Role.VENUE_STAFF))]
Db = Annotated[Session, Depends(get_db)]


def _user_id(user: dict[str, object]) -> uuid.UUID:
    return uuid.UUID(str(user["sub"]))


@router.get("", response_model=list[VenueBookingDecisionRead])
def list_booking_requests(user: VenueStaff, db: Db) -> list[VenueBookingDecisionRead]:
    del user
    return [VenueBookingDecisionRead.from_context(*row) for row in service.list_requests(db)]


@router.post("/{booking_id}/reject", response_model=VenueBookingDecisionRead)
def reject_booking_request(
    booking_id: uuid.UUID, body: VenueBookingReject, user: VenueStaff, db: Db
) -> VenueBookingDecisionRead:
    try:
        row = service.reject(db, booking_id, _user_id(user), body.reason, datetime.now(UTC))
    except service.BookingRequestNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Venue booking request not found") from exc
    except InvalidBookingTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return VenueBookingDecisionRead.from_context(*row)
