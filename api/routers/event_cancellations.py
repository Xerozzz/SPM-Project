"""Cancelling an event and its requests (SCRUM-115).

Its own module, like SCRUM-86's completion. Who may act is the access rule
(`REQUEST_EVENT_CANCELLATION`, `CANCEL_EVENT`, `READ_EVENT_CANCELLATION`), not a check
here.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import EventAccess, get_current_user, require_event_access
from domain.event_cancellation import CancellationRefusal
from models.event_request import EventRequest
from schemas.event_cancellations import (
    CancelInput,
    CancellationRead,
    CancellationRequestInput,
    CancellationRequestRead,
    DeclineInput,
)
from schemas.event_requests import FieldProblemRead
from services import event_cancellations as service

router = APIRouter(prefix="/event-requests", tags=["event-cancellation"])

OwnedEvent = Annotated[
    EventRequest, Depends(require_event_access(EventAccess.REQUEST_EVENT_CANCELLATION))
]
CancellableEvent = Annotated[EventRequest, Depends(require_event_access(EventAccess.CANCEL_EVENT))]
CancellationReader = Annotated[
    EventRequest, Depends(require_event_access(EventAccess.READ_EVENT_CANCELLATION))
]
CurrentUser = Annotated[dict[str, object], Depends(get_current_user)]
Db = Annotated[Session, Depends(get_db)]

# What the person is told when the event cannot be cancelled.
_REFUSALS = {
    CancellationRefusal.ALREADY_CANCELLED: "This event is already cancelled",
    CancellationRefusal.COMPLETED: "A completed event cannot be cancelled",
    CancellationRefusal.NOT_ACTIVE: (
        "Only a submitted, planning or confirmed event can be cancelled"
    ),
}


def _user_id(user: dict[str, object]) -> uuid.UUID:
    return uuid.UUID(str(user["sub"]))


def _invalid(exc: service.InvalidCancellationError) -> HTTPException:
    problems = [FieldProblemRead(field=p.field, reason=p.reason) for p in exc.problems]
    return HTTPException(422, [p.model_dump() for p in problems])


def _refused(exc: service.NotCancellableError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, _REFUSALS[exc.refusal])


def _no_request() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "No pending cancellation request with that id")


@router.post(
    "/{request_id}/cancellation-requests",
    response_model=CancellationRequestRead,
    status_code=201,
)
def request_cancellation(
    event: OwnedEvent, body: CancellationRequestInput, user: CurrentUser, db: Db
) -> CancellationRequestRead:
    """AC1: the owning Organiser asks for the event to be cancelled."""
    try:
        row = service.request_cancellation(
            db, event.id, _user_id(user), body.reason, datetime.now(UTC)
        )
    except service.NotCancellableError as exc:
        raise _refused(exc) from exc
    except service.InvalidCancellationError as exc:
        raise _invalid(exc) from exc
    except service.RequestAlreadyPendingError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A cancellation request is already waiting"
        ) from exc
    return CancellationRequestRead.model_validate(row)


@router.post("/{request_id}/cancel", response_model=CancellationRead)
def cancel(
    event: CancellableEvent, body: CancelInput, user: CurrentUser, db: Db
) -> CancellationRead:
    """AC1 to AC9: cancel the event and release everything it holds."""
    try:
        done = service.cancel(
            db, event.id, _user_id(user), body.reason, body.request_id, datetime.now(UTC)
        )
    except service.NotCancellableError as exc:
        raise _refused(exc) from exc
    except service.InvalidCancellationError as exc:
        raise _invalid(exc) from exc
    except service.RequestNotFoundError as exc:
        raise _no_request() from exc
    return CancellationRead.of(done, service.requests_of(db, done))


@router.post(
    "/{request_id}/cancellation-requests/{cancellation_id}/decline",
    response_model=CancellationRequestRead,
)
def decline(
    event: CancellableEvent,
    cancellation_id: uuid.UUID,
    body: DeclineInput,
    user: CurrentUser,
    db: Db,
) -> CancellationRequestRead:
    """AC1: decline a pending request with a note. The event is not changed."""
    try:
        row = service.decline(
            db, event.id, cancellation_id, _user_id(user), body.note, datetime.now(UTC)
        )
    except service.RequestNotFoundError as exc:
        raise _no_request() from exc
    except service.InvalidCancellationError as exc:
        raise _invalid(exc) from exc
    return CancellationRequestRead.model_validate(row)


@router.get("/{request_id}/cancellation", response_model=CancellationRead)
def read_cancellation(event: CancellationReader, db: Db) -> CancellationRead:
    """AC1, AC3: the cancellation and every request, for the people allowed to see it."""
    return CancellationRead.of(event, service.requests_of(db, event))
