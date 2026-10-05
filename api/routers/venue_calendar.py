"""Venue availability calendar for Coordinators and Venue Staff (SCRUM-54)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import require_role
from domain.roles import Role
from schemas.venue_calendar import CalendarEntryRead
from services import venue_calendar as service

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
        raise HTTPException(422, [problem.__dict__ for problem in exc.problems]) from exc
    return [CalendarEntryRead.model_validate(row) for row in rows]
