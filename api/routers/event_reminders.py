"""Arrangement reminders (SCRUM-85).

Its own module rather than more routes on the event-request router, which already
carries several stories. The paths sit under `/event-requests` because the schedule
belongs to an event; nothing here is shared with request creation or review.

AC2 is the access rule, not a check in this file: `MANAGE_REMINDERS` is the event's
current assigned Coordinator and nobody else, for reading as well as writing.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import EventAccess, get_current_user, require_event_access
from models.event_request import EventRequest
from schemas.event_reminders import ReminderRead, ReminderScheduleWrite
from schemas.event_requests import FieldProblemRead
from services import event_reminders as service

router = APIRouter(prefix="/event-requests", tags=["event-reminders"])

RemindableEvent = Annotated[
    EventRequest, Depends(require_event_access(EventAccess.MANAGE_REMINDERS))
]
CurrentUser = Annotated[dict[str, object], Depends(get_current_user)]
Db = Annotated[Session, Depends(get_db)]


def _user_id(user: dict[str, object]) -> uuid.UUID:
    return uuid.UUID(str(user["sub"]))


@router.get("/{request_id}/reminders", response_model=list[ReminderRead])
def read_schedule(event: RemindableEvent, db: Db) -> list[ReminderRead]:
    """AC2: the schedule as it stands, longest lead time first."""
    return [ReminderRead.of(row) for row in service.list_for_event(db, event)]


@router.put("/{request_id}/reminders", response_model=list[ReminderRead])
def write_schedule(
    event: RemindableEvent, body: ReminderScheduleWrite, user: CurrentUser, db: Db
) -> list[ReminderRead]:
    """AC1: replace the schedule, or refuse it whole.

    422 names every bad lead time at once and changes nothing, which is what AC1 means
    by refusing "without partial changes" — a list with one bad entry leaves the stored
    schedule exactly as it was rather than saving the good ones.
    """
    try:
        saved = service.configure(db, event, body.lead_minutes, _user_id(user), datetime.now(UTC))
    except service.InvalidReminderScheduleError as exc:
        problems = [FieldProblemRead(field=p.field, reason=p.reason) for p in exc.problems]
        raise HTTPException(422, [p.model_dump() for p in problems]) from exc
    return [ReminderRead.of(row) for row in saved]
