"""Confirming an event (SCRUM-80).

Its own module rather than more routes on the event-request router, which already
carries four stories: the paths sit under `/event-requests` because that is what is
being confirmed, but nothing here is shared with request creation or review.

AC1 is the access rule, not a check in this file: `CONFIRM_EVENT` is the event's current
assigned Coordinator and nobody else. Everything else is the service's answer.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import EventAccess, get_current_user, require_event_access
from models.event_request import EventRequest
from schemas.event_confirmations import ConfirmationRead, ConfirmationReadinessRead
from services import event_confirmations as service

router = APIRouter(prefix="/event-requests", tags=["event-confirmation"])

ConfirmableEvent = Annotated[EventRequest, Depends(require_event_access(EventAccess.CONFIRM_EVENT))]
CurrentUser = Annotated[dict[str, object], Depends(get_current_user)]
Db = Annotated[Session, Depends(get_db)]


def _user_id(user: dict[str, object]) -> uuid.UUID:
    return uuid.UUID(str(user["sub"]))


@router.get("/{request_id}/confirmation", response_model=ConfirmationReadinessRead)
def read_readiness(event: ConfirmableEvent, db: Db) -> ConfirmationReadinessRead:
    """AC2, AC3 and AC10: may this event be confirmed, and if not, what is missing.

    A read, so it reports rather than refuses: an event already Confirmed answers with
    `not_in_planning` instead of an error, which is what a screen needs to show the
    right thing on every card it has.
    """
    found = service.readiness(db, event, datetime.now(UTC))
    return ConfirmationReadinessRead.of(event, found)


@router.post("/{request_id}/confirm", response_model=ConfirmationRead)
def confirm(event: ConfirmableEvent, user: CurrentUser, db: Db) -> ConfirmationRead:
    """AC4: commit the event and its holds in one transaction.

    409 with every reason when something still stands in the way (AC2, AC3, AC7, AC10).
    The prerequisites are rechecked inside the service under a row lock, so this cannot
    confirm against the readiness the screen happened to be showing.
    """
    try:
        confirmed = service.confirm(db, event, _user_id(user), datetime.now(UTC))
    except service.NotConfirmableError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "reason": "not_confirmable",
                "arrangement_blockers": [row.value for row in exc.problems.arrangement],
                "safety_blockers": [row.value for row in exc.problems.safety],
            },
        ) from exc
    return ConfirmationRead.of(confirmed, service.confirmed_bookings_of(db, confirmed))
