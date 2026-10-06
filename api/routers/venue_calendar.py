"""Venue availability calendar for Coordinators and Venue Staff (SCRUM-54, SCRUM-76,
SCRUM-77)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import require_role
from domain.roles import Role
from schemas.venue_calendar import AvailabilityRead, CalendarEntryDetailsRead, CalendarEntryRead
from services import venue_calendar as service
from services import venues

router = APIRouter(prefix="/venue-calendar", tags=["venue-calendar"])

# AC3: Coordinators and Venue Staff only. Organisers and Attendees are refused.
Planner = Annotated[dict[str, object], Depends(require_role(Role.COORDINATOR, Role.VENUE_STAFF))]
Db = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[CalendarEntryRead])
def calendar(
    user: Planner, db: Db, start_at: datetime, end_at: datetime, venue_id: uuid.UUID | None = None
) -> list[CalendarEntryRead]:
    """AC1 and AC2: what holds the venue, or every venue, in [start_at, end_at)."""
    del user
    try:
        rows = service.entries(db, start_at, end_at, venue_id)
    except service.InvalidCalendarRangeError as exc:
        raise _http_error(exc) from exc
    return [CalendarEntryRead.model_validate(row) for row in rows]


@router.get("/availability", response_model=AvailabilityRead)
def availability(
    user: Planner, db: Db, venue_id: uuid.UUID, start_at: datetime, end_at: datetime
) -> AvailabilityRead:
    """SCRUM-76: is the venue free for the whole of [start_at, end_at)?"""
    del user
    try:
        result = service.availability(db, venue_id, start_at, end_at)
    except (service.InvalidCalendarRangeError, venues.VenueNotFoundError) as exc:
        raise _http_error(exc) from exc
    return AvailabilityRead.model_validate(result)


@router.get("/bookings/{booking_id}", response_model=CalendarEntryDetailsRead)
def booking_details(user: Planner, db: Db, booking_id: uuid.UUID) -> CalendarEntryDetailsRead:
    """SCRUM-77 AC1: a booking entry in full."""
    del user
    try:
        return CalendarEntryDetailsRead.model_validate(service.booking_details(db, booking_id))
    except service.CalendarEntryNotFoundError as exc:
        raise _http_error(exc) from exc


@router.get("/unavailabilities/{unavailability_id}", response_model=CalendarEntryDetailsRead)
def unavailability_details(
    user: Planner, db: Db, unavailability_id: uuid.UUID
) -> CalendarEntryDetailsRead:
    """SCRUM-77 AC1: a closure entry in full, with its reason."""
    del user
    try:
        details = service.unavailability_details(db, unavailability_id)
    except service.CalendarEntryNotFoundError as exc:
        raise _http_error(exc) from exc
    return CalendarEntryDetailsRead.model_validate(details)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, venues.VenueNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Venue not found")
    if isinstance(exc, service.CalendarEntryNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Calendar entry not found")
    assert isinstance(exc, service.InvalidCalendarRangeError)
    return HTTPException(422, [problem.__dict__ for problem in exc.problems])
