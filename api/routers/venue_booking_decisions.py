"""Venue Staff endpoints to review and reject venue booking requests (SCRUM-40), with
what would block approving each one (SCRUM-75), and to place tentative holds (SCRUM-83).

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
from domain.booking_conflict import BookingConflictError
from domain.roles import Role
from domain.venue_booking import InvalidBookingTransitionError
from domain.venue_hold import InactiveHoldError
from repositories import equipment_requirements as requirement_repo
from schemas.venue_booking_decisions import (
    VenueBookingDecisionRead,
    VenueBookingHold,
    VenueBookingReject,
)
from services import venue_booking_decisions as service
from services import venue_bookings

router = APIRouter(prefix="/venue-bookings", tags=["venue-booking-decisions"])

VenueStaff = Annotated[dict[str, object], Depends(require_role(Role.VENUE_STAFF))]
Db = Annotated[Session, Depends(get_db)]


def _user_id(user: dict[str, object]) -> uuid.UUID:
    return uuid.UUID(str(user["sub"]))


@router.get("", response_model=list[VenueBookingDecisionRead])
def list_booking_requests(user: VenueStaff, db: Db) -> list[VenueBookingDecisionRead]:
    del user
    items = service.list_requests(db)
    # One lookup for the whole queue rather than one per row: this lists every pending
    # booking at every venue, so a query per booking would grow with the backlog.
    requirements = requirement_repo.live_for_events(
        db, {event.id for (_booking, event, _venue), _conflict in items}
    )
    return [
        VenueBookingDecisionRead.from_context(*row, conflict, requirements.get(row[1].id, []))
        for row, conflict in items
    ]


@router.post("/{booking_id}/hold", response_model=VenueBookingDecisionRead)
def hold_booking_request(
    booking_id: uuid.UUID, body: VenueBookingHold, user: VenueStaff, db: Db
) -> VenueBookingDecisionRead:
    """SCRUM-83: put a pending request on a tentative hold until `expires_at` (AC1).
    A clash or a request that is not pending is 409, a bad expiry 422 (AC3)."""
    try:
        venue_bookings.hold(db, booking_id, _user_id(user), body.expires_at, datetime.now(UTC))
    except venue_bookings.BookingNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Venue booking request not found") from exc
    except venue_bookings.InvalidHoldError as exc:
        problems = [{"field": p.field, "reason": p.reason} for p in exc.problems]
        raise HTTPException(422, problems) from exc
    except (BookingConflictError, InvalidBookingTransitionError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    context = service.get(db, booking_id)
    return VenueBookingDecisionRead.from_context(
        *context, None, requirement_repo.list_for_event(db, context[1].id)
    )


@router.patch("/{booking_id}/hold", response_model=VenueBookingDecisionRead)
def update_hold_expiry(
    booking_id: uuid.UUID, body: VenueBookingHold, user: VenueStaff, db: Db
) -> VenueBookingDecisionRead:
    """SCRUM-121: revise the expiry of an active Tentative hold. SCRUM-136: recorded
    with the Venue Staff member who made the change."""
    try:
        venue_bookings.update_hold_expiry(
            db, booking_id, body.expires_at, datetime.now(UTC), _user_id(user)
        )
    except venue_bookings.BookingNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Venue booking request not found") from exc
    except venue_bookings.InvalidHoldError as exc:
        problems = [{"field": p.field, "reason": p.reason} for p in exc.problems]
        raise HTTPException(422, problems) from exc
    except InactiveHoldError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    context = service.get(db, booking_id)
    return VenueBookingDecisionRead.from_context(
        *context, None, requirement_repo.list_for_event(db, context[1].id)
    )


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
    return VenueBookingDecisionRead.from_context(
        *row, None, requirement_repo.list_for_event(db, row[1].id)
    )
