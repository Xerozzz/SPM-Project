"""Venue availability calendar for Coordinators and Venue Staff (SCRUM-54, SCRUM-76)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import require_role
from domain.roles import Role
from schemas.venue_calendar import AvailabilityRead, CalendarEntryRead
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


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, venues.VenueNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Venue not found")
    assert isinstance(exc, service.InvalidCalendarRangeError)
    return HTTPException(422, [problem.__dict__ for problem in exc.problems])
